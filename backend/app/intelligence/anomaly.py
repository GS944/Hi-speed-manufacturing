"""Job-work cost anomaly detection.

Two complementary detectors over annexure / job-work entries:
  * Isolation Forest on (operation, vendor, log unit cost, log qty, weight) - multivariate outliers
  * Robust z-score of unit cost within the same operation (median / MAD) - explains *why*
An entry is flagged when both agree, or when the robust z-score alone is extreme.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
from sklearn.ensemble import IsolationForest

_scores: dict[str, np.ndarray] = {}


def detect(entries: list[dict]) -> tuple[list[dict], dict]:
    rows = [e for e in entries if e.get("unit_cost") not in (None, 0) and e.get("operation")]
    if len(rows) < 30:
        return [], {"trained": False, "reason": "not enough job-work entries"}
    ops = {o: i for i, o in enumerate(sorted({e["operation"] for e in rows}))}
    vens = {v: i for i, v in enumerate(sorted({e.get("vendor") or "" for e in rows}))}
    X = np.array([[ops[e["operation"]], vens[e.get("vendor") or ""], math.log1p(e["unit_cost"]),
                   math.log1p(e.get("qty") or 0), e.get("weight") or 0] for e in rows])
    key = hashlib.sha256(X.tobytes()).hexdigest()
    iso = _scores.get(key)
    if iso is None:                              # unchanged job-work entries -> reuse the previous scores
        forest = IsolationForest(n_estimators=100, contamination=0.03, random_state=3).fit(X)
        iso = forest.decision_function(X)        # < 0 = anomalous
        _scores.clear()
        _scores[key] = iso
    by_op: dict[str, list[float]] = {}
    for e in rows:
        by_op.setdefault(e["operation"], []).append(math.log1p(e["unit_cost"]))
    stats = {}
    for op, vals in by_op.items():
        med = float(np.median(vals))
        mad = float(np.median(np.abs(np.array(vals) - med))) or 0.05
        stats[op] = (med, mad)
    flagged = []
    for e, s in zip(rows, iso):
        med, mad = stats[e["operation"]]
        z = 0.6745 * (math.log1p(e["unit_cost"]) - med) / mad
        if (s < 0 and abs(z) > 2.5) or abs(z) > 5:
            flagged.append({**e, "anomaly_score": round(float(-s), 3), "robust_z": round(z, 2),
                            "typical_unit_cost": round(math.expm1(med), 2),
                            "reason": f"Unit cost {e['unit_cost']:g} is {'above' if z > 0 else 'below'} the typical "
                                      f"{math.expm1(med):.2f} for {e['operation']}"})
    flagged.sort(key=lambda x: -abs(x["robust_z"]))
    return flagged, {"trained": True, "algorithm": "Isolation Forest + robust z-score (median/MAD)",
                     "entries": len(rows), "flagged": len(flagged), "operations": len(ops)}
