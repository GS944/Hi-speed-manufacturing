"""Order queries, serialisation and dashboard aggregates over the workspace."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from ..intelligence import nlq
from . import workspace

ROLE_LABELS: dict[str, str] = {}


def _iso(d):
    return d.isoformat() if isinstance(d, date) else d


def entry_json(e: dict) -> dict:
    return {k: _iso(v) for k, v in e.items() if k not in ("data", "fields")} | {"table_id": e["table_id"]}


def line_summary(ln: dict) -> dict:
    r, n = ln["roles"], ln["num"]
    return {
        "id": ln["id"], "table_id": ln["table_id"], "order_no": ln["key"], "row_no": ln["row_no"],
        "status": ln["status"], "stage": ln["stage"], "activity": ln["activity"],
        "customer": ln["customer"], "customer_code": r.get("customer_code"),
        "item": r.get("item_description"), "category": ln["canon"].get("category"),
        "order_type": ln["canon"].get("order_type"), "priority": ln["canon"].get("priority"), "urgent": ln["urgent"],
        "material": ln["canon"].get("material"), "order_qty": n.get("order_qty"), "despatch_qty": n.get("despatch_qty"),
        "order_date": _iso(ln["dates"].get("order_date")), "due_date": _iso(ln["dates"].get("due_date")),
        "despatch_date": _iso(ln["dates"].get("despatch_date")), "overdue_days": ln["overdue_days"],
        "colour": r.get("colour_tag"), "eta": ln.get("eta"), "job_work_count": len(ln["job_work"]),
        "open_at_vendor": sum(1 for e in ln["job_work"] if e["state"] == "at_vendor"),
    }


def line_detail(ln: dict, ws) -> dict:
    prof = ln["profile"] or {}
    fields = prof.get("fields", {})
    n = ln["num"]
    qty = {k: n.get(k) for k in ("order_qty", "issued_qty", "coating_qty", "reject_qty", "despatch_qty", "stock_qty") if k in fields}
    return line_summary(ln) | {
        "status_reason": ln["status_reason"],
        "stages": [{k: _iso(v) for k, v in s.items()} for s in ln["stages"]],
        "quantities": qty,
        "fields": fields,
        "record": ln["data"],
        "source": ws.tables.get(ln["table_id"], {}),
        "job_work": [entry_json(e) for e in ln["job_work"]],
        "customer_po": ln["roles"].get("customer_po"), "hardness": ln["roles"].get("hardness_spec"),
        "invoice_ref": ln["roles"].get("invoice_ref"),
    }


def order_payload(key: str) -> dict | None:
    ws = workspace.get()
    lines = ws.find(key)
    if not lines:
        return None
    status = "completed" if all(l["status"] == "completed" for l in lines) else "live"
    return {"order_no": lines[0]["key"], "status": status, "line_count": len(lines),
            "lines": [line_detail(l, ws) for l in lines], "generated_at": date.today().isoformat()}


def filter_lines(ws, q: str | None = None, status: str | None = None, customer: str | None = None,
                 priority: str | None = None, category: str | None = None, stage: str | None = None,
                 date_from: date | None = None, date_to: date | None = None, risk: str | None = None,
                 material: str | None = None) -> list[dict]:
    out = ws.lines
    if status == "overdue":
        out = [l for l in out if l["overdue_days"] > 0]
    elif status in ("live", "completed"):
        out = [l for l in out if l["status"] == status]
    if customer:
        c = customer.lower()
        out = [l for l in out if c in str(l["customer"]).lower() or c == str(l["roles"].get("customer_code", "")).lower()]
    if priority:
        out = [l for l in out if str(l["canon"].get("priority", "")).lower() == priority.lower()
               or (priority.lower() in ("urgent", "emergency") and l["urgent"])]
    if category:
        out = [l for l in out if str(l["canon"].get("category", "")).lower() == category.lower()]
    if material:
        out = [l for l in out if str(l["canon"].get("material", "")).lower() == material.lower()]
    if stage:
        out = [l for l in out if l["stage"] == stage]
    if risk:   # predicted to miss a due date that has not passed yet
        out = [l for l in out if (l.get("eta") or {}).get("late_risk") == risk and l["overdue_days"] == 0]
    if date_from:
        out = [l for l in out if l["dates"].get("order_date") and l["dates"]["order_date"] >= date_from]
    if date_to:
        out = [l for l in out if l["dates"].get("order_date") and l["dates"]["order_date"] <= date_to]
    if q:
        ql = q.lower().strip()
        out = [l for l in out if ql in l["key"].lower() or ql in str(l["roles"].get("item_description", "")).lower()
               or ql in str(l["customer"]).lower() or ql in str(l["roles"].get("customer_po", "")).lower()]
    return out


def dashboard() -> dict:
    ws = workspace.get()
    today = date.today()
    lines = ws.lines
    live = [l for l in lines if l["status"] == "live"]
    month_start = today.replace(day=1)
    kpi = {
        "total_lines": len(lines), "total_orders": len(ws.by_key),
        "live": len(live), "completed": len(lines) - len(live),
        "overdue": sum(1 for l in live if l["overdue_days"] > 0),
        "due_7d": sum(1 for l in live if l["dates"].get("due_date") and today <= l["dates"]["due_date"] <= today + timedelta(days=7)),
        "urgent_open": sum(1 for l in live if l["urgent"]),
        "at_vendor": sum(1 for e in ws.ledger if e["state"] == "at_vendor" and any(k in ws.by_key for k in e["refs"])),
        "high_risk": sum(1 for l in live if (l.get("eta") or {}).get("late_risk") == "high" and l["overdue_days"] == 0),
        "orders_this_month": sum(1 for l in lines if l["dates"].get("order_date") and l["dates"]["order_date"] >= month_start),
        "despatched_this_month": sum(1 for l in lines if l["dates"].get("despatch_date") and l["dates"]["despatch_date"] >= month_start),
        "jobwork_spend_month": round(sum((e["unit_cost"] or 0) * (e["qty"] or 0) for e in ws.ledger
                                         if e["issue_date"] and e["issue_date"] >= month_start), 2),
    }
    monthly = defaultdict(lambda: {"received": 0, "completed": 0, "live": 0, "despatched": 0})
    for l in lines:
        od = l["dates"].get("order_date")
        if od:
            m = monthly[od.strftime("%Y-%m")]
            m["received"] += 1
            m[l["status"]] += 1
        dd = l["dates"].get("despatch_date")
        if dd:
            monthly[dd.strftime("%Y-%m")]["despatched"] += 1
    months = sorted(monthly)[-12:]
    stage_counts = Counter(l["stage"] for l in live)
    stage_order = [s["label"] for s in (live[0]["stages"] if live else [])]
    by_customer = Counter(l["customer"] for l in live)
    ops = defaultdict(lambda: {"entries": 0, "spend": 0.0, "at_vendor": 0})
    for e in ws.ledger:
        if e["operation"]:
            o = ops[e["operation"]]
            o["entries"] += 1
            o["spend"] += (e["unit_cost"] or 0) * (e["qty"] or 0)
            o["at_vendor"] += e["state"] == "at_vendor"
    vend = Counter(e["vendor"] for e in ws.ledger if e["state"] == "at_vendor" and e["vendor"])
    at_risk = sorted([l for l in live if (l.get("eta") or {}).get("late_risk") in ("high", "medium") and l["overdue_days"] == 0],
                     key=lambda l: (l["dates"].get("due_date") or date.max))[:12]
    recent = sorted(lines, key=lambda l: (l["dates"].get("order_date") or date.min, l["id"]), reverse=True)[:8]
    return {
        "kpi": kpi,
        "monthly": [{"month": m} | monthly[m] for m in months],
        "stages": [{"stage": s, "count": stage_counts.get(s, 0)} for s in stage_order if stage_counts.get(s)],
        "top_customers": [{"customer": c, "live": n} for c, n in by_customer.most_common(8)],
        "operations": sorted(({"operation": k, **{kk: round(vv, 2) for kk, vv in v.items()}} for k, v in ops.items()),
                             key=lambda x: -x["spend"])[:10],
        "vendors_open": [{"vendor": v, "open": n} for v, n in vend.most_common(8)],
        "at_risk": [line_summary(l) for l in at_risk],
        "recent": [line_summary(l) for l in recent],
        "anomalies": [entry_json(a) for a in ws.anomalies[:8]],
        "models": {"eta": ws.eta.metrics, "anomaly": ws.anomaly_info},
        "built_at": ws.built_at,
    }


def ask(text: str) -> dict:
    ws = workspace.get()
    p = nlq.parse(text, ws)
    intent, ents = p["intent"], p["entities"]
    res: dict = {"query": text, "parsed": {k: (_iso(v)) for k, v in p.items()}, "intent": intent}
    if intent in ("track_order", "annexure"):
        if not p["order_no"]:
            return res | {"answer": "Which order number? Try “status of 2978”.", "kind": "message"}
        lines = ws.find(p["order_no"])
        if not lines:
            sug = ws.suggest(p["order_no"])
            return res | {"answer": f"Order {p['order_no']} was not found." + (f" Did you mean {', '.join(sug[:5])}?" if sug else ""), "kind": "message"}
        ln = lines[0]
        target = "annexure" if intent == "annexure" else "order"
        verb = "completed" if all(l["status"] == "completed" for l in lines) else "live"
        return res | {"kind": "navigate", "target": target, "order_no": ln["key"],
                      "answer": f"Order {ln['key']} is {verb.upper()} — {ln['stage']}. {ln['activity']}",
                      "rows": [line_summary(l) for l in lines]}
    if intent == "vendor_open":
        es = [e for e in ws.ledger if e["state"] == "at_vendor"]
        if "vendor" in ents:
            es = [e for e in es if e["vendor"] == ents["vendor"]]
        if "operation" in ents:
            es = [e for e in es if e["operation"] == ents["operation"]]
        es.sort(key=lambda e: e["issue_date"] or date.min)
        who = ents.get("vendor") or "vendors"
        return res | {"kind": "entries", "answer": f"{len(es)} job-work entr{'y' if len(es) == 1 else 'ies'} currently at {who}"
                      + (f" for {ents['operation']}" if 'operation' in ents else "") + ".",
                      "entries": [entry_json(e) for e in es[:200]]}
    if intent == "anomalies":
        return res | {"kind": "entries", "answer": f"{len(ws.anomalies)} job-work entries have unusual unit costs.",
                      "entries": [entry_json(a) for a in ws.anomalies[:200]]}
    if intent == "top_customers":
        ls = filter_lines(ws, status=p["status"], date_from=p["date_from"], date_to=p["date_to"])
        c = Counter(l["customer"] for l in ls).most_common(p["top"])
        return res | {"kind": "table", "answer": f"Top {len(c)} customers by order lines" + (f" ({p['period']})" if p["period"] else "") + ".",
                      "columns": ["Customer", "Order lines"], "table": [[a, b] for a, b in c]}
    status = "live" if intent == "at_risk" else p["status"]
    ls = filter_lines(ws, status=status, customer=ents.get("customer"), priority=ents.get("priority"),
                      category=ents.get("category"), material=ents.get("material"),
                      date_from=p["date_from"], date_to=p["date_to"], risk="high" if intent == "at_risk" else None)
    desc = " ".join(x for x in [ents.get("priority"), {"live": "live", "completed": "completed", "overdue": "overdue"}.get(status or ""),
                                "order lines", f"for {ents['customer']}" if ents.get("customer") else None,
                                f"in {ents['category']}" if ents.get("category") else None,
                                f"in {ents['material']}" if ents.get("material") else None,
                                f"({p['period']})" if p["period"] else None,
                                "predicted to miss the due date" if intent == "at_risk" else None] if x)
    if intent == "count_orders":
        return res | {"kind": "count", "answer": f"{len(ls)} {desc}.", "count": len(ls),
                      "filters": {"status": status, **ents}}
    ls = sorted(ls, key=lambda l: (l["dates"].get("order_date") or date.min), reverse=True)
    return res | {"kind": "orders", "answer": f"{len(ls)} {desc}.", "rows": [line_summary(l) for l in ls[:300]],
                  "filters": {"status": status, **ents}}
