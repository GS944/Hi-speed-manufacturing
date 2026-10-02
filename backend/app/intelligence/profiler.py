"""Turns a raw table into a JSON *profile* - the configuration the rest of the app runs on.

1. The neural classifier scores every (column, role) pair.
2. Columns are assigned to roles one-to-one with the Hungarian algorithm (scipy
   linear_sum_assignment) maximising total log-likelihood; columns whose best option is weaker than
   an "unassigned" slot stay unmapped.
3. The table type (order book, job-work ledger, vendor master, ...) is chosen by a weighted evidence
   score over the roles present (weights come from the ontology).
4. Stage pipeline and completion rules are instantiated from the ontology templates, keeping only
   the stages whose roles exist in this table.
"""
from __future__ import annotations

import math
import re
from datetime import datetime

import numpy as np
from scipy.optimize import linear_sum_assignment

from . import column_model

UNASSIGNED_P = 0.30
MULTI_ROLES = {"remarks", "address"}      # roles that may legitimately occur on several columns


def assign_roles(columns: list[str], values: list[list]) -> tuple[dict[str, str], dict[str, float], list[dict]]:
    P, classes = column_model.predict_proba(list(zip(columns, values)))
    P = np.asarray(P, dtype=float)
    n = len(columns)
    single = [c for c in classes if c not in MULTI_ROLES and c != "unknown"]
    # cost matrix: n columns x (single roles + n "multi/unassigned" slots)
    cost = np.full((n, len(single) + n), 1e3)
    multi_choice = []
    for i in range(n):
        p = dict(zip(classes, P[i].tolist()))
        for j, r in enumerate(single):
            cost[i, j] = -math.log(max(p[r], 1e-9))
        best_multi = max(MULTI_ROLES, key=lambda r: p.get(r, 0))
        pm = p.get(best_multi, 0)
        if pm >= max(UNASSIGNED_P, p.get("unknown", 0)):
            multi_choice.append((best_multi, pm))
            cost[i, len(single) + i] = -math.log(pm)
        else:
            multi_choice.append((None, max(UNASSIGNED_P, p.get("unknown", 0))))
            cost[i, len(single) + i] = -math.log(max(UNASSIGNED_P, p.get("unknown", 0)))
    rows, cols = linear_sum_assignment(cost)
    fields: dict[str, str] = {}
    conf: dict[str, float] = {}
    per_column = []
    for i, j in sorted(zip(rows, cols)):
        if j < len(single):
            role, pr = single[j], float(math.exp(-cost[i, j]))
        else:
            role, pr = multi_choice[i][0], float(multi_choice[i][1])
        top = sorted(zip(classes, P[i].tolist()), key=lambda t: -t[1])[:3]
        per_column.append({"column": columns[i], "role": role, "confidence": round(pr, 3),
                           "alternatives": [{"role": r, "p": round(float(q), 3)} for r, q in top]})
        if role and role not in fields:          # multi roles: first column is the primary one
            fields[role] = columns[i]
            conf[role] = round(pr, 3)
    return fields, conf, per_column


def multi_fields(per_column: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in per_column:
        if c["role"] in MULTI_ROLES:
            out.setdefault(c["role"], []).append(c["column"])
    return out


def classify_table(fields: dict[str, str], conf: dict[str, float], n_cols: int, n_rows: int, onto: dict) -> tuple[str, float, dict]:
    scores = {}
    for t, spec in onto["table_types"].items():
        if spec.get("max_columns") and n_cols > spec["max_columns"]:
            continue
        if n_rows < spec.get("min_rows", 0):
            continue
        if any(r not in fields for r in spec.get("required", [])):
            continue
        w = spec.get("weights", {})
        total = sum(w.values()) or 1
        scores[t] = sum(wt * conf.get(r, 0) for r, wt in w.items() if r in fields) / total
    if n_cols <= 2:
        scores.setdefault("lookup_list", 0.35)
    if not scores:
        return "unknown", 0.0, {}
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0)
    confidence = round(min(1.0, 0.5 * ranked[0] + 0.5 + 0.5 * margin) if best != "lookup_list" else 0.6, 3)
    if ranked[0] < 0.25 and best != "lookup_list":
        return "unknown", round(ranked[0], 3), scores
    return best, confidence, {k: round(v, 3) for k, v in scores.items()}


def _usable(spec: dict, fields: dict) -> bool:
    if any(r not in fields for r in spec.get("requires", [])):
        return False
    if spec.get("requires_any") and not any(r in fields for r in spec["requires_any"]):
        return False
    if any(r in fields for r in spec.get("only_if_missing", [])):
        return False
    return True


def build_profile(table_type: str, type_conf: float, fields: dict, conf: dict, per_column: list,
                  values_by_col: dict[str, list], sheet: str, onto: dict, type_scores: dict) -> dict:
    tspec = onto["table_types"].get(table_type, {})
    profile: dict = {
        "engine": "ml-mlp/hungarian",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "table_type": table_type,
        "type_label": tspec.get("label", "Unclassified table"),
        "type_confidence": type_conf,
        "type_scores": type_scores,
        "fields": fields,
        "multi_fields": multi_fields(per_column),
        "field_confidence": conf,
        "columns": per_column,
        "key": {"role": tspec.get("key_role"), "mode": tspec.get("key_mode", "none")} if tspec else {"role": None, "mode": "none"},
    }
    if table_type == "orders":
        stages = []
        for st in onto["stage_templates"]:
            if st.get("source") == "linked_ledger" or _usable(st, fields):
                stages.append({k: v for k, v in st.items() if k not in ("requires", "requires_any")})
        profile["stages"] = stages
        profile["completion"] = [r for r in onto["completion_rules"] if _usable(r, fields)]
        profile["derived"] = discover_derived(fields, values_by_col)
        pr = fields.get("priority")
        if pr:
            vals = {str(v) for v in values_by_col.get(pr, []) if v}
            profile["urgent_values"] = sorted(v for v in vals if any(t in v.lower() for t in onto["urgent_terms"]))
    if table_type == "job_work_ledger":
        profile["link"] = {"to": "orders", "ref_role": "order_no", "parse": "multi_ref",
                           "date_tolerance_days": onto["ledger_link"]["date_tolerance_days"]}
    return profile


QTY_ROLES = ["order_qty", "issued_qty", "coating_qty", "reject_qty", "despatch_qty", "stock_qty", "quantity"]


def discover_derived(fields: dict, values_by_col: dict[str, list], min_support: int = 30) -> list[dict]:
    """Find quantity columns that are arithmetic functions of others (spreadsheet formulas such as
    Reject = Issued - Coated, Stock = Issued - Reject - Despatched). Exhaustive search over
    target = a - b and target = a - b - c, accepted when it holds on >= 98% of rows where the target
    is filled (blank operands count as 0). Only near-fully-filled columns can be targets, which
    separates the real formula from its algebraic mirror images. Recomputed on every edit."""
    def num(v):
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    roles = [r for r in QTY_ROLES if r in fields]
    cols = {r: [num(v) for v in values_by_col.get(fields[r], [])] for r in roles}
    out = []
    for t in roles:
        tv = cols[t]
        idx = [i for i, v in enumerate(tv) if v is not None]
        # a formula column is filled on (almost) every row, input columns have gaps
        if len(idx) < min_support or len(idx) < 0.9 * len(tv):
            continue
        others = [r for r in roles if r != t]
        best = None
        for a in others:
            for subs in [(b,) for b in others if b != a] + [(b, c) for b in others for c in others if len({a, b, c}) == 3 and b < c]:
                ok = sum(1 for i in idx if abs(tv[i] - ((cols[a][i] or 0) - sum(cols[s][i] or 0 for s in subs))) < 1e-6)
                informative = sum(1 for i in idx if cols[a][i] and any(cols[s][i] for s in subs))
                if ok / len(idx) >= 0.98 and informative >= min_support // 3:
                    if best is None or len(subs) < len(best[1]):
                        best = (a, subs, ok / len(idx))
        if best:
            out.append({"target": t, "plus": best[0], "minus": list(best[1]), "support": round(best[2], 4)})
    # order so that a relation is computed after the relations it depends on
    ordered, pending = [], out[:]
    while pending:
        done = {d["target"] for d in ordered}
        nxt = next((d for d in pending if not ({d["plus"], *d["minus"]} & {p["target"] for p in pending if p is not d} - done)), pending[0])
        ordered.append(nxt)
        pending.remove(nxt)
    return ordered


def title_for(table_type: str, sheet: str, onto: dict) -> str:
    label = onto["table_types"].get(table_type, {}).get("label")
    return f"{label} · {sheet}" if label else sheet


# ----------------------------------------------------------------------------- forms (print templates)
GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")


def extract_form(cells: list[tuple[int, int, object]]) -> dict:
    """Extract an organisation identity + document structure from a printable template."""
    grid: dict[tuple[int, int], object] = {(r, c): v for r, c, v in cells}
    texts = [(r, c, str(v)) for r, c, v in cells if isinstance(v, str)]
    out: dict = {"labels": [], "copies": [], "title": None, "company": {}}
    for r, c, s in texts:
        u = s.upper()
        if "COPY" in u and len(s) < 40:
            out["copies"].append(s.strip())
        if re.search(r"(CHALLAN|INVOICE|ROUTE\s+CARD|DELIVERY|ANNEXURE|PURCHASE ORDER)", u) and len(s) < 60 and not out["title"]:
            out["title"] = s.strip()
        if s.rstrip().endswith(("-", ":")):
            out["labels"].append(s.strip(" -:"))
    m = next((g for _, _, s in texts for g in GSTIN_RE.findall(s)), None)
    # company block: text starting with M/s. followed by address lines in the same column
    for r, c, s in sorted(texts):
        if re.match(r"^m/?s\.?\s", s, re.I):
            lines = []
            rr = r + 1
            while isinstance(grid.get((rr, c)), str) and len(lines) < 5 and not GSTIN_RE.search(str(grid[(rr, c)])):
                lines.append(str(grid[(rr, c)]).strip())
                rr += 1
            out["company"] = {"name": re.sub(r"^m/?s\.?\s*", "", s, flags=re.I).strip(), "address": lines}
            break
    if m:
        out["company"]["gstin"] = m
    for r, c, s in texts:
        if re.search(r"tar+if|hsn|sac", s, re.I):
            below = grid.get((r + 1, c))
            if isinstance(below, (int, float)):
                out["tariff_code"] = str(int(below))
    seen = set()
    out["copies"] = [x for x in out["copies"] if not (x in seen or seen.add(x))]
    out["labels"] = list(dict.fromkeys(out["labels"]))[:30]
    return out
