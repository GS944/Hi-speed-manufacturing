"""In-memory analytical workspace.

Built from the database on demand and cached until data changes (any upload, edit or mapping
change calls `invalidate()`). It joins order lines with their job-work (annexure) entries, evaluates
the JSON stage / completion rules from each table profile, canonicalises categories, resolves
customer names, trains the ETA model, runs anomaly detection and data-quality checks.
"""
from __future__ import annotations

import bisect
import logging
import threading
import time
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import DataFile, DataTable, Record, SessionLocal, Setting
from ..intelligence import anomaly, canonical, rules
from ..intelligence.eta import EtaModel
from .keys import norm_key, parse_refs, to_date, to_num

log = logging.getLogger("ordertrack.workspace")

DATE_ROLES = {"order_date", "due_date", "coating_date", "despatch_date", "issue_date", "inward_date"}
NUM_ROLES = {"order_qty", "issued_qty", "coating_qty", "reject_qty", "despatch_qty", "stock_qty", "quantity",
             "unit_cost", "value_of_goods", "weight", "old_price"}
CANON_ROLES = {"category", "order_type", "material", "priority", "operation", "vendor_name", "hardness_spec", "colour_tag"}

_lock = threading.RLock()
_cache: "Workspace | None" = None


def _db_version() -> int:
    with SessionLocal() as db:
        return int(db.scalar(select(Setting.value).where(Setting.key == "data_version")) or 0)


def invalidate() -> None:
    """Bump the data version in the database so every server process/worker rebuilds."""
    with SessionLocal() as db:
        row = db.get(Setting, "data_version")
        if row:
            row.value = int(row.value or 0) + 1
        else:
            db.add(Setting(key="data_version", value=1))
        db.commit()


def peek() -> "Workspace | None":
    """The last built workspace, possibly stale, without triggering a rebuild (cheap; for list/status screens)."""
    return _cache


def get() -> "Workspace":
    global _cache
    version = _db_version()
    with _lock:
        if _cache is None or _cache.version != version:
            t0 = time.time()
            ws = Workspace(version)
            ws.build()
            _cache = ws
            log.info("workspace built in %.2fs (%d order lines, %d job-work entries)",
                     time.time() - t0, len(ws.lines), len(ws.ledger))
        return _cache


def _parse_date(v, ref_low=date(2000, 1, 1), ref_high=date(2100, 1, 1)):
    d = to_date(v)
    return d if d and ref_low <= d <= ref_high else None


class Workspace:
    def __init__(self, version: int):
        self.version = version
        self.lines: list[dict] = []
        self.by_key: dict[str, list[dict]] = defaultdict(list)
        self.sorted_keys: list[str] = []
        self.lex_keys: list[str] = []
        self.ledger: list[dict] = []
        self.ledger_by_key: dict[str, list[dict]] = defaultdict(list)
        self.customers: dict[str, str] = {}
        self.vendors: dict[str, dict] = {}
        self.tables: dict[int, dict] = {}
        self.eta = EtaModel()
        self.anomalies: list[dict] = []
        self.anomaly_info: dict = {}
        self.quality: dict[int, dict] = {}
        self.canon: dict[str, dict[str, str]] = {}
        self.built_at = None
        self.duplicates_skipped = 0

    # ------------------------------------------------------------------ build
    def build(self) -> None:
        with SessionLocal() as db:
            tables = db.scalars(select(DataTable).join(DataFile).where(
                DataTable.active.is_(True), DataFile.status == "ready", DataTable.kind == "table")).all()
            files = {f.id: f for f in db.scalars(select(DataFile)).all()}
            recs: dict[int, list[Record]] = defaultdict(list)
            for r in db.scalars(select(Record).where(Record.table_id.in_([t.id for t in tables]))):
                recs[r.table_id].append(r)
        for t in tables:
            self.tables[t.id] = {"id": t.id, "title": t.title, "sheet": t.sheet_name, "role": t.role,
                                 "file": files[t.file_id].original_name if t.file_id in files else "", "profile": t.profile}
        # masters first
        for t in tables:
            f = (t.profile or {}).get("fields", {})
            if t.role == "customer_master" and "customer_code" in f and "customer_name" in f:
                for r in recs[t.id]:
                    k = norm_key(r.data.get(f["customer_code"]))
                    if k and r.data.get(f["customer_name"]):
                        self.customers[k] = str(r.data[f["customer_name"]])
            if t.role == "vendor_master" and "vendor_name" in f:
                mf = (t.profile or {}).get("multi_fields", {})
                for r in recs[t.id]:
                    name = r.data.get(f["vendor_name"])
                    if name:
                        self.vendors[str(name).strip().upper()] = {
                            "name": str(name).strip(),
                            "address": [str(r.data[c]) for c in mf.get("address", []) if r.data.get(c)],
                            "gstin": r.data.get(f.get("gstin", ""), "")}
        for t in tables:
            if t.role == "job_work_ledger":
                self._load_ledger(t, recs[t.id])
        for t in sorted(tables, key=lambda t: -t.id):        # newest first: wins on exact duplicates
            if t.role == "orders":
                self._load_orders(t, recs[t.id])
        self._canonicalise()
        self._link_and_evaluate()
        self.sorted_keys = sorted(self.by_key, key=_key_sort)
        self.lex_keys = sorted(self.by_key)
        try:
            # instant when the completed-order history is unchanged (cached model); otherwise train in the
            # background so pages are never blocked - forecasts appear as soon as training finishes
            if self.eta.fit(self.lines, allow_train=False):
                self.eta.predict(self.lines)
            else:
                threading.Thread(target=self._train_eta, daemon=True, name="eta-train").start()
        except Exception as e:  # noqa: BLE001
            log.warning("ETA model failed: %s", e)
        try:
            self.anomalies, self.anomaly_info = anomaly.detect(self.ledger)
        except Exception as e:  # noqa: BLE001
            log.warning("anomaly detection failed: %s", e)
        self._quality(tables, recs)
        self.built_at = time.time()

    def _extract(self, t: DataTable, r: Record) -> tuple[dict, dict, dict]:
        f = (t.profile or {}).get("fields", {})
        roles = {role: r.data.get(col) for role, col in f.items()}
        dates = {k: _parse_date(v) for k, v in roles.items() if k in DATE_ROLES}
        nums = {k: to_num(v) for k, v in roles.items() if k in NUM_ROLES}
        return roles, dates, nums

    def _train_eta(self) -> None:
        try:
            t0 = time.time()
            if self.eta.fit(self.lines):
                self.eta.predict(self.lines)
            log.info("ETA model trained in background in %.1fs", time.time() - t0)
        except Exception as e:  # noqa: BLE001
            log.warning("ETA model failed: %s", e)

    def _load_ledger(self, t: DataTable, records: list[Record]) -> None:
        f = (t.profile or {}).get("fields", {})
        for r in records:
            roles, dates, nums = self._extract(t, r)
            refs = parse_refs(roles.get("order_no"))
            hc = roles.get("hardness_checked")
            e = {"id": r.id, "table_id": t.id, "row_no": r.row_no, "refs": refs, "raw_ref": roles.get("order_no"),
                 "doc_no": roles.get("doc_no") or roles.get("serial_no"), "issue_date": dates.get("issue_date"),
                 "vendor": (str(roles["vendor_name"]).strip() if roles.get("vendor_name") else None),
                 "operation": (str(roles["operation"]).strip() if roles.get("operation") else None),
                 "material": roles.get("material"), "description": roles.get("item_description"),
                 "qty": nums.get("quantity") or nums.get("issued_qty") or nums.get("order_qty"),
                 "unit_cost": nums.get("unit_cost"), "value_of_goods": nums.get("value_of_goods"),
                 "hrc_spec": roles.get("hardness_spec"), "hrc_checked": hc, "weight": nums.get("weight"),
                 "inward_doc": roles.get("inward_doc"), "inward_date": dates.get("inward_date"),
                 "customer_code": norm_key(roles.get("customer_code")), "remarks": roles.get("remarks"),
                 "tariff": roles.get("tariff_code"), "hrc_result": hrc_verdict(roles.get("hardness_spec"), hc),
                 "data": r.data, "fields": f}
            e["state"] = "returned" if e["inward_date"] or (e["inward_doc"] and not f.get("inward_date")) else "at_vendor"
            self.ledger.append(e)
            for k in refs:
                self.ledger_by_key[k].append(e)

    def _load_orders(self, t: DataTable, records: list[Record]) -> None:
        for r in records:
            roles, dates, nums = self._extract(t, r)
            key = norm_key(roles.get("order_no"))
            if not key:
                continue
            # the same order line loaded from two files (e.g. a re-saved copy kept alongside) counts once
            if any(o["data"] == r.data and o["table_id"] != t.id for o in self.by_key.get(key, [])):
                self.duplicates_skipped += 1
                continue
            # Sheets often derive reject = issued - coated by formula; before coating/despatch is
            # recorded that value is "not yet inspected", not a rejection.
            if nums.get("reject_qty") and nums.get("coating_qty") is None and nums.get("despatch_qty") is None:
                nums["reject_qty"] = None
            ln = {"id": r.id, "table_id": t.id, "row_no": r.row_no, "key": key, "roles": roles, "dates": dates,
                  "num": nums, "data": r.data, "canon": {}, "profile": t.profile}
            cc = norm_key(roles.get("customer_code"))
            ln["customer"] = roles.get("customer_name") or self.customers.get(cc) or (f"Customer {cc}" if cc else "—")
            self.lines.append(ln)
            self.by_key[key].append(ln)
        self.lines.sort(key=lambda l: (l["table_id"], l["row_no"]))

    def _canonicalise(self) -> None:
        for role in CANON_ROLES:
            vals = [ln["roles"].get(role) for ln in self.lines] + [e.get({"operation": "operation", "vendor_name": "vendor"}.get(role, "_")) for e in self.ledger]
            self.canon[role] = canonical.canonical_map(vals)
        for ln in self.lines:
            for role in CANON_ROLES:
                v = ln["roles"].get(role)
                if v not in (None, ""):
                    ln["canon"][role] = self.canon[role].get(str(v).strip(), str(v))
        for e in self.ledger:
            if e["operation"]:
                e["operation"] = self.canon["operation"].get(e["operation"], e["operation"])
            if e["vendor"]:
                e["vendor"] = self.canon["vendor_name"].get(e["vendor"], e["vendor"])

    # ------------------------------------------------------------------ status engine
    def _link_and_evaluate(self) -> None:
        today = date.today()
        for ln in self.lines:
            prof = ln["profile"] or {}
            tol = timedelta(days=(prof.get("link") or {}).get("date_tolerance_days", 3))
            od = ln["dates"].get("order_date")
            jw = [e for e in self.ledger_by_key.get(ln["key"], [])
                  if not od or not e["issue_date"] or e["issue_date"] >= od - tol]
            # an order number reused across financial years: keep entries closest to this order
            ln["job_work"] = sorted(jw, key=lambda e: (e["issue_date"] or date.min, e["id"]))
            get = lambda role, _ln=ln: _ln["roles"].get(role) if role not in DATE_ROLES else _ln["dates"].get(role)
            complete_rule = next((c for c in prof.get("completion", []) if rules.evaluate(c["when"], get)), None)
            ln["status"] = "completed" if complete_rule else "live"
            ln["status_reason"] = complete_rule["label"] if complete_rule else "Work in progress"
            stages = []
            for st in prof.get("stages", []):
                if st.get("source") == "linked_ledger":
                    if not ln["job_work"]:
                        stages.append({"key": st["key"], "label": st["label"], "done": False, "detail": "No job-work DC raised yet", "skippable": True})
                        continue
                    open_ = [e for e in ln["job_work"] if e["state"] == "at_vendor"]
                    stages.append({"key": st["key"], "label": st["label"], "done": not open_, "in_progress": bool(open_),
                                   "date": max((e["issue_date"] for e in ln["job_work"] if e["issue_date"]), default=None),
                                   "detail": f"{len(ln['job_work'])} operation(s), {len(open_)} at vendor"})
                    continue
                done = rules.evaluate(st["when"], get)
                stages.append({"key": st["key"], "label": st["label"], "done": done,
                               "date": ln["dates"].get(st.get("date_role")) if st.get("date_role") else None,
                               "qty": ln["num"].get(st.get("qty_role")) if st.get("qty_role") else None,
                               "detail": st.get("detail")})
            # a later stage being done implies the earlier ones happened (e.g. issued not recorded)
            last_done = max((i for i, s in enumerate(stages) if s["done"]), default=-1)
            for i, s in enumerate(stages):
                s["state"] = ("done" if s["done"] or (i < last_done and not s.get("in_progress")) else
                              "current" if s.get("in_progress") else "pending")
                if s["state"] == "pending" and s.get("skippable") and i < last_done:
                    s["state"] = "skipped"
            if ln["status"] == "completed":
                for s in stages:
                    if s["state"] in ("pending", "current"):
                        s["state"] = "skipped" if s.get("skippable") or s["state"] == "pending" else "done"
            else:
                cur = next((i for i, s in enumerate(stages) if s["state"] == "current"), None)
                if cur is None:
                    cur = next((i for i, s in enumerate(stages) if s["state"] == "pending"), len(stages) - 1)
                    if 0 <= cur < len(stages):
                        stages[cur]["state"] = "current"
            ln["stages"] = stages
            cur_stage = next((s for s in stages if s["state"] == "current"), None)
            ln["stage"] = "Completed" if ln["status"] == "completed" else (cur_stage["label"] if cur_stage else "In progress")
            ln["activity"] = self._activity(ln, cur_stage)
            due = ln["dates"].get("due_date")
            ln["overdue_days"] = (today - due).days if due and ln["status"] == "live" and due < today else 0
            pv = ln["roles"].get("priority")
            ln["urgent"] = bool(pv and str(pv) in set(prof.get("urgent_values", [])))

    def _activity(self, ln: dict, cur: dict | None) -> str:
        if ln["status"] == "completed":
            d = ln["dates"].get("despatch_date")
            return f"Despatched{' on ' + d.strftime('%d %b %Y') if d else ''} — {ln['status_reason'].lower()}."
        open_ = [e for e in ln["job_work"] if e["state"] == "at_vendor"]
        if open_:
            e = open_[-1]
            since = f" since {e['issue_date'].strftime('%d %b %Y')}" if e["issue_date"] else ""
            return f"{e['operation'] or 'Job work'} at {e['vendor'] or 'vendor'}{since} (DC {e['doc_no']})."
        n = ln["num"]
        if n.get("despatch_qty") and n.get("order_qty") and n["despatch_qty"] < n["order_qty"]:
            return f"Partially despatched: {n['despatch_qty']:g} of {n['order_qty']:g}."
        if cur:
            if cur["key"] == "coating" and ln["job_work"]:
                last = ln["job_work"][-1]
                return f"Job work complete (last: {last['operation']}). Awaiting coating / finishing."
            return f"Next step: {cur['label']}."
        return "In progress."

    # ------------------------------------------------------------------ data quality
    def _quality(self, tables, recs) -> None:
        known = set(self.by_key)
        for t in tables:
            f = (t.profile or {}).get("fields", {})
            issues: list[dict] = []

            def add(rule, severity, rows, msg):
                if rows:
                    issues.append({"rule": rule, "severity": severity, "count": len(rows), "message": msg,
                                   "sample_rows": sorted(rows)[:25]})
            rows = recs[t.id]
            if t.role == "orders":
                tl = [ln for ln in self.lines if ln["table_id"] == t.id]
                seen = defaultdict(list)
                for ln in tl:
                    seen[ln["key"]].append(ln["row_no"])
                add("duplicate_key", "warning", [r for v in seen.values() if len(v) > 1 for r in v],
                    "Order number used on more than one line")
                for role in ("order_date", "despatch_date", "coating_date", "due_date"):
                    col = f.get(role)
                    if col:
                        bad = [r.row_no for r in rows if r.data.get(col) not in (None, "") and _parse_date(r.data.get(col)) is None]
                        add(f"invalid_{role}", "error", bad, f"'{col}' is not a valid date")
                add("despatch_before_order", "error",
                    [ln["row_no"] for ln in tl if ln["dates"].get("despatch_date") and ln["dates"].get("order_date")
                     and ln["dates"]["despatch_date"] < ln["dates"]["order_date"]], "Despatch date is before the order date")
                add("despatch_exceeds_issued", "warning",
                    [ln["row_no"] for ln in tl if (ln["num"].get("despatch_qty") or 0) > (ln["num"].get("issued_qty") or 1e18)],
                    "Despatched quantity is greater than the issued quantity")
                add("negative_qty", "error",
                    [ln["row_no"] for ln in tl if any((ln["num"].get(k) or 0) < 0 for k in NUM_ROLES)], "Negative quantity")
                for role in ("customer_code", "item_description", "order_qty"):
                    col = f.get(role)
                    if col:
                        add(f"missing_{role}", "warning", [r.row_no for r in rows if r.data.get(col) in (None, "")], f"'{col}' is blank")
                add("overdue", "info", [ln["row_no"] for ln in tl if ln["overdue_days"] > 0], "Live order past its due date")
            elif t.role == "job_work_ledger":
                tl = [e for e in self.ledger if e["table_id"] == t.id]
                add("unlinked_reference", "warning", [e["row_no"] for e in tl if e["refs"] and not any(k in known for k in e["refs"])],
                    "Order number does not exist in any loaded order book (may belong to a previous year)")
                add("missing_order_ref", "warning", [e["row_no"] for e in tl if not e["refs"]], "No order number on the entry")
                add("missing_unit_cost", "warning", [e["row_no"] for e in tl if not e["unit_cost"]], "Unit cost missing or zero")
                add("inward_before_issue", "error", [e["row_no"] for e in tl if e["inward_date"] and e["issue_date"] and e["inward_date"] < e["issue_date"]],
                    "Inward date is before the issue date")
                add("hrc_out_of_spec", "error", [e["row_no"] for e in tl if e["hrc_result"] == "out_of_spec"], "Measured hardness outside the specified range")
                add("open_at_vendor_30d", "info", [e["row_no"] for e in tl if e["state"] == "at_vendor" and e["issue_date"]
                                                    and (date.today() - e["issue_date"]).days > 30], "Material at vendor for more than 30 days")
            errors = sum(i["count"] for i in issues if i["severity"] == "error")
            warns = sum(i["count"] for i in issues if i["severity"] == "warning")
            n = max(len(rows), 1)
            self.quality[t.id] = {"table_id": t.id, "rows": len(rows), "issues": issues,
                                  "score": round(max(0.0, 100 - 100 * (errors + 0.4 * warns) / n), 1)}

    # ------------------------------------------------------------------ queries
    def find(self, q: str) -> list[dict]:
        k = norm_key(q)
        return self.by_key.get(k, []) if k else []

    def suggest(self, q: str, limit: int = 8) -> list[str]:
        """Prefix search over order numbers using binary search on the sorted key list."""
        k = norm_key(q) or ""
        if not k:
            return []
        lex = self.lex_keys
        i = bisect.bisect_left(lex, k)
        out = []
        while i < len(lex) and lex[i].startswith(k) and len(out) < limit:
            out.append(lex[i])
            i += 1
        return out


def _key_sort(k: str):
    return (0, int(k), "") if k.isdigit() else (1, 0, k)


def hrc_verdict(spec, measured) -> str | None:
    import re
    if not spec or not measured:
        return None
    ms = re.findall(r"\d{2}(?:\.\d)?", str(spec))
    mm = re.findall(r"\d{2}(?:\.\d)?", str(measured))
    if len(ms) < 2 or not mm:
        return None
    lo, hi = sorted(float(x) for x in ms[:2])
    vals = [float(x) for x in mm[:2]]
    return "ok" if all(lo <= v <= hi for v in vals) else "out_of_spec"
