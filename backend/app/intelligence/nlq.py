"""Natural-language command bar - without any external AI service.

  1. Intent classification: TF-IDF (word 1-2 grams + char 2-5 grams) -> logistic regression,
     trained on utterances generated from templates (below).
  2. Slot filling: regex for numbers / dates, fuzzy gazetteer matching (rapidfuzz) for customers,
     vendors, operations, priorities, categories and materials taken from the live data.
  3. The structured query is executed against the workspace.
"""
from __future__ import annotations

import random
import re
import threading
from datetime import date, timedelta

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

TEMPLATES = {
    "track_order": ["status of order {n}", "where is order {n}", "track {n}", "track order {n}", "{n}",
                    "what is happening with {n}", "order {n} status", "show order {n}", "which stage is {n} in",
                    "is order {n} completed", "live status {n}", "progress of job {n}", "order no {n}", "check {n}"],
    "list_orders": ["show {st} orders", "list {st} orders for {e}", "{st} orders of {e}", "{e} {st} orders",
                    "show orders for {e}", "orders from {e}", "{p} orders", "show {p} orders that are {st}",
                    "list all {st} jobs", "orders {st} {t}", "orders received {t}", "show me {e} orders {t}",
                    "find orders with {e}", "{st} {p} orders for {e}", "all orders"],
    "count_orders": ["how many orders are {st}", "how many {st} orders for {e}", "count of {st} orders",
                     "number of orders {t}", "total orders for {e}", "how many {p} orders", "count {st} jobs {t}",
                     "how many orders did {e} place {t}"],
    "annexure": ["annexure for {n}", "annexure of order {n}", "print annexure {n}", "job work for order {n}",
                 "dc for {n}", "delivery challan {n}", "operations done on {n}", "download annexure {n}",
                 "show annexure details for {n}", "which vendor has {n}"],
    "vendor_open": ["what is at {v}", "pending at {v}", "material at vendor {v}", "jobs with {v}",
                    "open dcs at {v}", "what is pending with vendors", "items at vendor", "material lying at vendors",
                    "{o} pending at vendors", "which jobs are out for {o}", "show {o} jobs at vendor"],
    "top_customers": ["top customers", "top {k} customers", "which customer has most orders", "best customers {t}",
                      "customers with most pending orders", "customer wise orders", "biggest customers by quantity"],
    "anomalies": ["unusual costs", "price anomalies", "abnormal unit cost", "suspicious job work rates",
                  "cost outliers", "wrong unit price entries", "anomalies in annexure"],
    "at_risk": ["orders likely to be late", "at risk orders", "delay risk", "which orders will miss due date",
                "predicted late orders", "orders at risk for {e}", "late orders forecast", "delayed orders prediction"],
}
FILL = {
    "st": ["live", "pending", "open", "completed", "done", "despatched", "overdue", "late", "in progress", "closed"],
    "p": ["emergency", "urgent", "regular", "within 1 week"],
    "e": ["taegutec", "tungaloy", "classic engineering", "widia", "mikron", "kanchi tools", "customer 2324", "dolphin"],
    "v": ["globe-tech", "coastal heat treatment", "rapid tooling", "kshipra", "vinayaka", "sri jyothi grinders"],
    "o": ["heat treatment", "grinding", "blank milling", "coolant hole", "turning", "tip seat"],
    "t": ["today", "this week", "this month", "last 30 days", "in august", "last month", "yesterday"],
    "k": ["5", "10", "3"],
    "n": [],
}

STATUS_WORDS = {"live": "live", "pending": "live", "open": "live", "in progress": "live", "wip": "live", "running": "live",
                "active": "live", "completed": "completed", "complete": "completed", "done": "completed",
                "despatched": "completed", "dispatched": "completed", "closed": "completed", "delivered": "completed",
                "overdue": "overdue", "late": "overdue", "delayed": "overdue"}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}

_model = None
_lock = threading.Lock()


def _train():
    global _model
    rng = random.Random(5)
    X, y = [], []
    for intent, tpls in TEMPLATES.items():
        for _ in range(60):
            t = rng.choice(tpls)
            s = re.sub(r"\{(\w+)\}", lambda m: str(rng.randint(1, 4999)) if m.group(1) == "n" else rng.choice(FILL[m.group(1)]), t)
            if rng.random() < 0.3:
                s = rng.choice(["please ", "can you ", "show me ", "i want ", ""]) + s
            X.append(s.lower())
            y.append(intent)
    feats = FeatureUnion([("w", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                          ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True))])
    _model = Pipeline([("f", feats), ("clf", LogisticRegression(C=6, max_iter=2000))]).fit(X, y)


def classify(text: str) -> tuple[str, float]:
    with _lock:
        if _model is None:
            _train()
    s = re.sub(r"\d+", lambda m: m.group(0), text.lower())
    probs = _model.predict_proba([s])[0]
    i = probs.argmax()
    return _model.classes_[i], float(probs[i])


def _date_range(text: str) -> tuple[date | None, date | None, str | None]:
    t, today = text.lower(), date.today()
    if "today" in t:
        return today, today, "today"
    if "yesterday" in t:
        d = today - timedelta(days=1)
        return d, d, "yesterday"
    if "this week" in t:
        s = today - timedelta(days=today.weekday())
        return s, today, "this week"
    if "last week" in t:
        s = today - timedelta(days=today.weekday() + 7)
        return s, s + timedelta(days=6), "last week"
    if "this month" in t:
        return today.replace(day=1), today, "this month"
    if "last month" in t:
        e = today.replace(day=1) - timedelta(days=1)
        return e.replace(day=1), e, "last month"
    m = re.search(r"last (\d+) days", t)
    if m:
        return today - timedelta(days=int(m.group(1))), today, f"last {m.group(1)} days"
    for name, num in MONTHS.items():
        if re.search(rf"\b{name[:3]}\w*\b", t) and not (name == "may" and re.search(r"\bmay be\b", t)):
            y = today.year if num <= today.month else today.year - 1
            s = date(y, num, 1)
            e = (date(y + (num == 12), num % 12 + 1, 1) - timedelta(days=1))
            return s, e, name.title()
    return None, None, None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&]+", " ", s.lower())).strip()


def _gazetteer_match(text: str, gaz: dict[str, list[str]]) -> dict[str, str]:
    """Fuzzy-match n-grams of the query against known entity values.

    Candidates: a query span matches a value when it is similar (Levenshtein ratio >= 88) to the
    whole value, or to the value's leading words ("globe-tech" -> "Globe-Tech Fortune Industries").
    Resolution: greedy interval scheduling - best-scoring candidates first, each query word may be
    used by one entity only and each slot is filled once.
    """
    words = _norm(text).split()
    stop = {"orders", "order", "show", "list", "the", "for", "how", "many", "with", "from", "all", "jobs", "job",
            "pending", "at", "vendor", "vendors", "last", "days", "this", "month", "week", "top", "customers",
            "customer", "of", "in", "status", "where", "is", "are", "what"}
    cands = []
    for n in (4, 3, 2, 1):
        for i in range(len(words) - n + 1):
            g = " ".join(words[i:i + n])
            if len(g) < 3 or g.replace(" ", "").isdigit() or g in STATUS_WORDS or all(w in stop for w in g.split()):
                continue
            for slot, values in gaz.items():
                for v in values:
                    nv = _norm(v)
                    full = fuzz.ratio(g, nv)
                    head = " ".join(nv.split()[:n])
                    part = fuzz.ratio(g, head) - (0 if len(head) >= 5 else 15) - 4   # prefix match ranks below full
                    score = max(full, part)
                    if score >= 88:
                        cands.append((score, n, slot, v, i, i + n))
    cands.sort(key=lambda c: (-c[0], -c[1]))
    used, found = set(), {}
    for score, n, slot, v, a, b in cands:
        if slot in found or any(k in used for k in range(a, b)):
            continue
        found[slot] = v
        used.update(range(a, b))
    return found


def parse(text: str, ws) -> dict:
    intent, conf = classify(text)
    low = text.lower()
    nums = [m for m in re.findall(r"\b\d{1,7}\b", low)]
    m_top = re.search(r"top (\d+)", low)
    if m_top:
        nums = [n for n in nums if n != m_top.group(1)]
    nums = [n for n in nums if not re.search(rf"last {n} days", low)]
    status = None
    for w, s in sorted(STATUS_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{w}\b", low):
            status = s
            break
    start, end, period = _date_range(low)
    gaz = {
        "customer": sorted(set(ws.customers.values()) | {ln["customer"] for ln in ws.lines if ln["customer"] != "—"}),
        "vendor": sorted({e["vendor"] for e in ws.ledger if e["vendor"]}),
        "operation": sorted({e["operation"] for e in ws.ledger if e["operation"]}),
        "priority": sorted({ln["canon"].get("priority") for ln in ws.lines if ln["canon"].get("priority")}),
        "category": sorted({ln["canon"].get("category") for ln in ws.lines if ln["canon"].get("category")}),
        "material": sorted({ln["canon"].get("material") for ln in ws.lines if ln["canon"].get("material")}),
    }
    ents = _gazetteer_match(low, gaz)
    code = re.search(r"customer\s*(?:code)?\s*(\d{3,6})", low)
    if code and ents.get("category", "").lower().startswith("customer"):
        ents.pop("category")          # "customer 2301" names a customer, not the CUSTOMER SPARES category
    if code and code.group(1) in ws.customers:
        ents["customer"] = ws.customers[code.group(1)]
        nums = [n for n in nums if n != code.group(1)]
    # an order number alone is a tracking request
    if nums and intent not in ("annexure",) and (intent in ("list_orders", "count_orders") and not ents and not status) and ws.find(nums[0]):
        intent = "track_order"
    if intent in ("list_orders", "top_customers") and "vendor" in ents and "customer" not in ents and re.search(r"\bat\b|vendor", low):
        intent = "vendor_open"
    return {"intent": intent, "confidence": round(conf, 3), "order_no": nums[0] if nums else None,
            "status": status, "date_from": start, "date_to": end, "period": period,
            "entities": ents, "top": int(m_top.group(1)) if m_top else 10}
