"""Upload processing: workbook -> tables -> ML profile -> records + key index."""
from __future__ import annotations

import logging
import re
import threading
import traceback

from sqlalchemy import delete, insert, select

from ..db import DataFile, DataTable, Record, RecordKey, SessionLocal, get_setting, set_setting, utcnow
from ..intelligence import column_model, profiler
from ..services import storage, workspace
from ..services.keys import norm_key, parse_refs
from .reader import column_stats, infer_dtype, read_workbook, segment_sheet, to_json_value

log = logging.getLogger("ordertrack.ingest")
_lock = threading.Lock()


def process_file_async(file_id: int) -> None:
    threading.Thread(target=process_file, args=(file_id,), daemon=True, name=f"ingest-{file_id}").start()


def resume_interrupted() -> None:
    """Re-queue uploads left in 'processing' by a restart or redeploy (processing is idempotent)."""
    with SessionLocal() as db:
        ids = list(db.scalars(select(DataFile.id).where(DataFile.status == "processing")))
    for fid in ids:
        log.info("resuming interrupted processing of file %s", fid)
        process_file_async(fid)


def process_file(file_id: int) -> None:
    with _lock, SessionLocal() as db:
        f = db.get(DataFile, file_id)
        if not f:
            return
        try:
            onto = column_model.load_ontology()
            with storage.get().local_copy(f.stored_name) as path:
                sheets = read_workbook(path)
            db.execute(delete(DataTable).where(DataTable.file_id == f.id))
            for sheet in sheets:
                for raw in segment_sheet(sheet):
                    _store_table(db, f, raw, onto)
            f.status = "ready"
            f.error = None
            f.processed_at = utcnow()
            db.commit()
        except Exception as e:  # noqa: BLE001 - surface any parsing problem to the admin
            db.rollback()
            f = db.get(DataFile, file_id)
            f.status = "error"
            f.error = f"{type(e).__name__}: {e}"
            db.commit()
            log.error("processing %s failed\n%s", file_id, traceback.format_exc())
        workspace.invalidate()


def _store_table(db, f: DataFile, raw, onto: dict) -> None:
    if raw.kind == "form":
        form = profiler.extract_form(raw.form_cells or [])
        form["cells"] = [[r, c, to_json_value(v)] for r, c, v in raw.form_cells or []]
        form["merged"] = raw.merged or []
        t = DataTable(file_id=f.id, sheet_name=raw.sheet, block_index=raw.block_index, range_ref=raw.range_ref,
                      header_row=raw.header_row, n_rows=0, kind="form", role="document_template", role_confidence=0.9,
                      title=f"{form.get('title') or 'Print template'} · {raw.sheet}", columns=[], profile={"table_type": "document_template"},
                      form=form)
        db.add(t)
        db.flush()
        company = form.get("company") or {}
        if company.get("name") and not get_setting(db, "company"):
            set_setting(db, "company", {"name": company["name"], "address": company.get("address", []),
                                        "gstin": company.get("gstin", ""), "short_name": "".join(w[0] for w in re.split(r"[\s-]+", company["name"]) if w[:1].isalpha()).upper()})
        if form.get("title") and "DELIVERY" in form["title"].upper() and not get_setting(db, "annexure_template"):
            set_setting(db, "annexure_template", {"title": form["title"], "copies": form.get("copies", []),
                                                  "tariff_code": form.get("tariff_code", ""), "source": raw.sheet})
        return
    if not raw.rows:
        return

    col_values = [[r[i] for r in raw.rows] for i in range(len(raw.columns))]
    sample = [v[:400] for v in col_values]          # classifier sample
    fields, conf, per_col = profiler.assign_roles(raw.columns, sample)
    ttype, tconf, scores = profiler.classify_table(fields, conf, len(raw.columns), len(raw.rows), onto)
    profile = profiler.build_profile(ttype, tconf, fields, conf, per_col, dict(zip(raw.columns, col_values)), raw.sheet, onto, scores)
    columns = []
    for name, letter, vals in zip(raw.columns, raw.letters, col_values):
        dt = infer_dtype(vals)
        columns.append({"name": name, "letter": letter, "dtype": dt, "stats": column_stats(vals, dt)})
    t = DataTable(file_id=f.id, sheet_name=raw.sheet, block_index=raw.block_index, range_ref=raw.range_ref,
                  header_row=raw.header_row, n_rows=len(raw.rows), kind="table", role=ttype, role_confidence=tconf,
                  title=profiler.title_for(ttype, raw.sheet, onto), columns=columns, profile=profile)
    db.add(t)
    db.flush()
    now = utcnow()
    batch = [{"table_id": t.id, "row_no": rn, "data": {c: to_json_value(v) for c, v in zip(raw.columns, r) if v is not None},
              "created_at": now, "updated_at": now} for r, rn in zip(raw.rows, raw.row_numbers)]
    for i in range(0, len(batch), 2000):
        db.execute(insert(Record), batch[i:i + 2000])
    db.flush()
    reindex_table(db, t)


def reindex_table(db, t: DataTable) -> None:
    """(Re)build the key index for one table from its profile."""
    db.execute(delete(RecordKey).where(RecordKey.table_id == t.id))
    key = (t.profile or {}).get("key") or {}
    col = (t.profile or {}).get("fields", {}).get(key.get("role") or "")
    if not col or key.get("mode") not in ("primary", "reference", "lookup"):
        return
    rows = db.execute(select(Record.id, Record.data).where(Record.table_id == t.id)).all()
    out = []
    for rid, data in rows:
        v = data.get(col)
        keys = parse_refs(v) if key["mode"] == "reference" else [norm_key(v)]
        out += [{"table_id": t.id, "record_id": rid, "key": k[:120], "kind": "ref" if key["mode"] == "reference" else "pk"}
                for k in keys if k]
    for i in range(0, len(out), 5000):
        db.execute(insert(RecordKey), out[i:i + 5000])


def reindex_record(db, t: DataTable, rec: Record) -> None:
    db.execute(delete(RecordKey).where(RecordKey.record_id == rec.id))
    key = (t.profile or {}).get("key") or {}
    col = (t.profile or {}).get("fields", {}).get(key.get("role") or "")
    if not col:
        return
    v = rec.data.get(col)
    keys = parse_refs(v) if key.get("mode") == "reference" else [norm_key(v)]
    for k in keys:
        if k:
            db.add(RecordKey(table_id=t.id, record_id=rec.id, key=k[:120], kind="ref" if key.get("mode") == "reference" else "pk"))

