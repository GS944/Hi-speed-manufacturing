"""Orders, live tracking, annexure / route-card documents, print jobs, dashboard, insights, ask."""
from __future__ import annotations

import io
import csv
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import AuditLog, DataTable, PrintJob, Record, User, get_db, get_setting, set_setting
from ..ingest import pipeline
from ..intelligence import column_model
from ..services import documents, orders, workspace
from ..services.keys import to_date, to_num

router = APIRouter(prefix="/api", tags=["orders"])

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _date(s: str | None) -> date | None:
    return to_date(s) if s else None


# ----------------------------------------------------------------------------- orders
@router.get("/orders")
def list_orders(q: str | None = None, status: str | None = None, customer: str | None = None, priority: str | None = None,
                category: str | None = None, stage: str | None = None, risk: str | None = None,
                date_from: str | None = None, date_to: str | None = None, sort: str = "order_date", dir: str = "desc",
                page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500), _: User = Depends(require_admin)):
    ws = workspace.get()
    ls = orders.filter_lines(ws, q=q, status=status, customer=customer, priority=priority, category=category, stage=stage,
                             risk=risk, date_from=_date(date_from), date_to=_date(date_to))
    rows = [orders.line_summary(l) for l in ls]
    numeric = {"order_qty", "despatch_qty", "overdue_days", "job_work_count"}

    def key(r):
        v = r.get(sort)
        if sort == "order_no":
            return (0, int(v), "") if str(v).isdigit() else (1, 0, str(v))
        if v is None:
            return (1, 0, "")
        return (0, v, "") if sort in numeric else (0, 0, str(v).lower())
    rows.sort(key=key, reverse=dir == "desc")
    total = len(rows)
    return {"total": total, "page": page, "size": size, "rows": rows[(page - 1) * size: page * size]}


@router.get("/orders/facets")
def facets(_: User = Depends(require_admin)):
    ws = workspace.get()
    def uniq(fn):
        return sorted({v for v in map(fn, ws.lines) if v})
    stages = []
    for l in ws.lines:
        for s in l["stages"]:
            if s["label"] not in stages:
                stages.append(s["label"])
    return {"customers": uniq(lambda l: l["customer"] if l["customer"] != "—" else None),
            "priorities": uniq(lambda l: l["canon"].get("priority")), "categories": uniq(lambda l: l["canon"].get("category")),
            "stages": stages + ["Completed"]}


@router.get("/orders/suggest")
def suggest(q: str, _: User = Depends(require_admin)):
    ws = workspace.get()
    keys = ws.suggest(q, 8)
    out = []
    for k in keys:
        l = ws.by_key[k][0]
        out.append({"order_no": k, "status": l["status"], "customer": l["customer"], "item": l["roles"].get("item_description")})
    return out


@router.get("/orders/export")
def export_orders(status: str | None = None, customer: str | None = None, q: str | None = None, priority: str | None = None,
                  category: str | None = None, stage: str | None = None, _: User = Depends(require_admin)):
    ws = workspace.get()
    ls = orders.filter_lines(ws, q=q, status=status, customer=customer, priority=priority, category=category, stage=stage)
    cols = ["order_no", "status", "stage", "activity", "customer", "item", "category", "priority", "order_qty", "despatch_qty",
            "order_date", "due_date", "despatch_date", "overdue_days", "job_work_count", "open_at_vendor"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c.replace("_", " ").title() for c in cols] + ["Expected Completion (ML)", "Late Risk (ML)"])
    for l in ls:
        s = orders.line_summary(l)
        w.writerow([s.get(c) if s.get(c) is not None else "" for c in cols] + [(s["eta"] or {}).get("expected", ""), (s["eta"] or {}).get("late_risk", "")])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="orders-{date.today().isoformat()}.csv"'})


@router.get("/orders/{order_no}")
def get_order(order_no: str, _: User = Depends(require_admin)):
    p = orders.order_payload(order_no)
    if not p:
        sug = workspace.get().suggest(order_no, 6)
        raise HTTPException(404, {"message": f"Order {order_no} was not found.", "suggestions": sug})
    return p


class ProgressIn(BaseModel):
    values: dict[str, object] = Field(description="role -> new value, e.g. {'despatch_qty': 10, 'despatch_date': '2026-10-01'}")


@router.patch("/orders/line/{record_id}")
def update_progress(record_id: int, body: ProgressIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Update an order line by semantic role; the role is translated to the sheet column via the profile."""
    rec = db.get(Record, record_id)
    if not rec:
        raise HTTPException(404, "Order line not found.")
    t = db.get(DataTable, rec.table_id)
    fields = (t.profile or {}).get("fields", {})
    dtypes = {c["name"]: c["dtype"] for c in t.columns}
    data, changes = dict(rec.data), {}
    for role, v in body.values.items():
        col = fields.get(role)
        if not col:
            raise HTTPException(400, f"This order book has no column mapped to '{role}'.")
        if v in (None, ""):
            new = None
        elif dtypes.get(col) == "date" or role.endswith("_date"):
            d = to_date(v)
            if not d:
                raise HTTPException(400, f"{role.replace('_', ' ')} must be a valid date.")
            new = d.isoformat()
        elif role.endswith("_qty"):
            n = to_num(v)
            if n is None or n < 0:
                raise HTTPException(400, f"{role.replace('_', ' ')} must be a non-negative number.")
            new = int(n) if n.is_integer() else n
        else:
            new = str(v).strip()
        if data.get(col) != new:
            changes[col] = {"from": data.get(col), "to": new}
        if new is None:
            data.pop(col, None)
        else:
            data[col] = new
    # recompute columns the pipeline discovered to be formulas of others (e.g. stock = issued - reject - despatch)
    for rel in (t.profile or {}).get("derived", []):
        if all(r in fields for r in [rel["target"], rel["plus"], *rel["minus"]]):
            val = (to_num(data.get(fields[rel["plus"]])) or 0) - sum(to_num(data.get(fields[m])) or 0 for m in rel["minus"])
            val = int(val) if float(val).is_integer() else val
            if data.get(fields[rel["target"]]) != val:
                changes[fields[rel["target"]]] = {"from": data.get(fields[rel["target"]]), "to": val, "derived": True}
            data[fields[rel["target"]]] = val
    rec.data = data
    pipeline.reindex_record(db, t, rec)
    db.add(AuditLog(username=user.username, action="update_progress", entity="order", entity_id=str(record_id), detail={"changes": changes}))
    db.commit()
    workspace.invalidate()
    key = workspace.get().lines and next((l["key"] for l in workspace.get().lines if l["id"] == record_id), None)
    return orders.order_payload(key) if key else {"ok": True}


# ----------------------------------------------------------------------------- annexure + route card
def _fy(d: date) -> str:
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y % 100:02d}-{(y + 1) % 100:02d}"


def _next_doc_no(db: Session, prefix: str) -> str:
    fy = _fy(date.today())
    n = db.scalar(select(func.count()).select_from(PrintJob).where(PrintJob.doc_no.like(f"{prefix}/{fy}/%"))) or 0
    return f"{prefix}/{fy}/{n + 1:05d}"


def _ids(entries: str | None) -> list[int] | None:
    return [int(x) for x in entries.split(",") if x.strip().isdigit()] if entries else None


@router.get("/annexure/{order_no}")
def annexure(order_no: str, entries: str | None = None, _: User = Depends(require_admin)):
    p = documents.annexure_payload(order_no, _ids(entries))
    if not p:
        raise HTTPException(404, f"Order {order_no} was not found.")
    return p


@router.get("/annexure/{order_no}/download")
def annexure_download(order_no: str, format: str = "pdf", entries: str | None = None, copies: str = "original",
                      _: User = Depends(require_admin)):
    p = documents.annexure_payload(order_no, _ids(entries))
    if not p:
        raise HTTPException(404, f"Order {order_no} was not found.")
    if format == "xlsx":
        return Response(documents.annexure_xlsx(p), media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="Annexure-{p["order_no"]}.xlsx"'})
    cps = p["company"]["copies"] if copies == "all" else [p["company"]["copies"][0] if p["company"]["copies"] else "ORIGINAL"]
    return Response(documents.annexure_pdf(p, cps), media_type=PDF,
                    headers={"Content-Disposition": f'attachment; filename="Annexure-{p["order_no"]}.pdf"'})


class SubmitIn(BaseModel):
    entry_ids: list[int] | None = None
    copies: list[str] | None = None


@router.post("/annexure/{order_no}/submit")
def annexure_submit(order_no: str, body: SubmitIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = documents.annexure_payload(order_no, body.entry_ids)
    if not p:
        raise HTTPException(404, f"Order {order_no} was not found.")
    p["doc_no"] = _next_doc_no(db, "ANX")
    copies = body.copies or p["company"]["copies"][:1] or ["ORIGINAL"]
    job = PrintJob(doc_no=p["doc_no"], kind="annexure", order_key=p["order_no"], payload=p | {"print_copies": copies},
                   copies=len(copies), created_by=user.username)
    db.add(job)
    db.add(AuditLog(username=user.username, action="print_annexure", entity="order", entity_id=p["order_no"], detail={"doc_no": p["doc_no"]}))
    db.commit()
    return {"job_id": job.id, "doc_no": job.doc_no, "payload": job.payload, "pdf_url": f"/api/print-jobs/{job.id}/pdf"}


@router.get("/route-card/{order_no}")
def route_card(order_no: str, _: User = Depends(require_admin)):
    p = documents.route_card_payload(order_no)
    if not p:
        raise HTTPException(404, f"Order {order_no} was not found.")
    return p


@router.post("/route-card/{order_no}/submit")
def route_card_submit(order_no: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = documents.route_card_payload(order_no)
    if not p:
        raise HTTPException(404, f"Order {order_no} was not found.")
    p["doc_no"] = _next_doc_no(db, "RC")
    job = PrintJob(doc_no=p["doc_no"], kind="route_card", order_key=p["order_no"], payload=p, copies=1, created_by=user.username)
    db.add(job)
    db.add(AuditLog(username=user.username, action="print_route_card", entity="order", entity_id=p["order_no"], detail={"doc_no": p["doc_no"]}))
    db.commit()
    return {"job_id": job.id, "doc_no": job.doc_no, "payload": p, "pdf_url": f"/api/print-jobs/{job.id}/pdf"}


@router.get("/route-card/{order_no}/download")
def route_card_download(order_no: str, _: User = Depends(require_admin)):
    p = documents.route_card_payload(order_no)
    if not p:
        raise HTTPException(404, f"Order {order_no} was not found.")
    return Response(documents.route_card_pdf(p), media_type=PDF,
                    headers={"Content-Disposition": f'attachment; filename="RouteCard-{p["order_no"]}.pdf"'})


@router.get("/print-jobs")
def print_jobs(kind: str | None = None, q: str | None = None, page: int = 1, size: int = 50,
               _: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(PrintJob).order_by(PrintJob.created_at.desc())
    if kind:
        stmt = stmt.where(PrintJob.kind == kind)
    if q:
        stmt = stmt.where((PrintJob.order_key == q.strip().upper()) | PrintJob.doc_no.contains(q.strip().upper()))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    jobs = db.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    return {"total": total, "rows": [{"id": j.id, "doc_no": j.doc_no, "kind": j.kind, "order_no": j.order_key, "copies": j.copies,
                                      "entries": len(j.payload.get("rows", [])) if j.kind == "annexure" else len(j.payload.get("cards", [])),
                                      "amount": (j.payload.get("totals") or {}).get("amount"), "status": j.status,
                                      "created_by": j.created_by, "created_at": j.created_at.isoformat()} for j in jobs]}


@router.get("/print-jobs/{job_id}")
def print_job(job_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    j = db.get(PrintJob, job_id)
    if not j:
        raise HTTPException(404, "Print job not found.")
    return {"id": j.id, "doc_no": j.doc_no, "kind": j.kind, "payload": j.payload, "created_at": j.created_at.isoformat()}


@router.get("/print-jobs/{job_id}/pdf")
def print_job_pdf(job_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    j = db.get(PrintJob, job_id)
    if not j:
        raise HTTPException(404, "Print job not found.")
    pdf = documents.annexure_pdf(j.payload, j.payload.get("print_copies")) if j.kind == "annexure" else documents.route_card_pdf(j.payload)
    name = j.doc_no.replace("/", "-")
    return Response(pdf, media_type=PDF, headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


# ----------------------------------------------------------------------------- dashboard / insights / ask
@router.get("/dashboard")
def dashboard(_: User = Depends(require_admin)):
    return orders.dashboard()


class AskIn(BaseModel):
    q: str = Field(min_length=1, max_length=300)


@router.post("/ask")
def ask(body: AskIn, _: User = Depends(require_admin)):
    return orders.ask(body.q)


@router.get("/insights")
def insights(_: User = Depends(require_admin)):
    ws = workspace.get()
    return {"column_model": column_model.model_info(), "eta": ws.eta.metrics, "anomaly": ws.anomaly_info,
            "anomalies": [orders.entry_json(a) for a in ws.anomalies[:300]],
            "nlq": {"algorithm": "TF-IDF (word + char n-grams) → logistic regression; fuzzy gazetteer slot filling",
                    "intents": ["track_order", "list_orders", "count_orders", "annexure", "vendor_open", "top_customers", "anomalies", "at_risk"]},
            "canonical_groups": {role: _groups(m) for role, m in ws.canon.items()}}


def _groups(m: dict[str, str]) -> list[dict]:
    g: dict[str, list[str]] = {}
    for raw, canon in m.items():
        g.setdefault(canon, []).append(raw)
    return [{"canonical": k, "variants": sorted(v)} for k, v in g.items() if len(v) > 1]


@router.post("/insights/retrain")
def retrain(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    info = column_model.train(force=True)
    workspace.invalidate()
    ws = workspace.get()
    db.add(AuditLog(username=user.username, action="retrain_models"))
    db.commit()
    return {"column_model": {k: v for k, v in info.items() if k != "clf"}, "eta": ws.eta.metrics, "anomaly": ws.anomaly_info}


# ----------------------------------------------------------------------------- settings / audit
class SettingsIn(BaseModel):
    company: dict | None = None
    annexure_template: dict | None = None


@router.get("/settings")
def get_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"company": get_setting(db, "company") or {}, "annexure_template": get_setting(db, "annexure_template") or {}}


@router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.company is not None:
        c = body.company
        set_setting(db, "company", {"name": str(c.get("name", "")).strip(), "short_name": str(c.get("short_name", "")).strip(),
                                    "gstin": str(c.get("gstin", "")).strip(),
                                    "address": [str(a).strip() for a in c.get("address", []) if str(a).strip()]})
    if body.annexure_template is not None:
        a = body.annexure_template
        set_setting(db, "annexure_template", {"title": str(a.get("title", "")), "tariff_code": str(a.get("tariff_code", "")),
                                              "copies": [str(x).strip() for x in a.get("copies", []) if str(x).strip()]})
    db.add(AuditLog(username=user.username, action="update_settings"))
    db.commit()
    return get_settings(user, db)


@router.get("/audit")
def audit(page: int = 1, size: int = 50, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(AuditLog))
    rows = db.scalars(select(AuditLog).order_by(AuditLog.at.desc()).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "rows": [{"id": a.id, "at": a.at.isoformat(), "user": a.username, "action": a.action,
                                      "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail} for a in rows]}
