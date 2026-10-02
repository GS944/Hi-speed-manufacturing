"""Lead-time (ETA) prediction for live orders.

Gradient-boosted regression trees (HistGradientBoostingRegressor) learn the number of days from
order date to despatch from completed order lines, using whichever attributes the profile mapped
(customer, order type, category, material, hardness, priority, quantity, planned lead time, number
of job-work operations, month). A second model with quantile loss gives a pessimistic (P80) bound.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold, cross_val_predict

CAT_ROLES = ["customer_code", "order_type", "category", "material", "hardness_spec", "priority"]


class EtaModel:
    def __init__(self):
        self.ready = False
        self.metrics: dict = {}
        self.vocab: dict[str, dict[str, int]] = {}

    def _row(self, line: dict) -> list[float]:
        r = line["roles"]
        feats = []
        for role in CAT_ROLES:
            v = line["canon"].get(role) or r.get(role)
            feats.append(self.vocab.get(role, {}).get(str(v), -1) if v not in (None, "") else -1)
        qty = line["num"].get("order_qty") or line["num"].get("issued_qty") or 0
        od, dd = line["dates"].get("order_date"), line["dates"].get("due_date")
        planned = (dd - od).days if od and dd else -1
        feats += [math.log1p(max(qty, 0)), planned, len(line.get("job_work", [])),
                  od.month if od else -1, od.weekday() if od else -1]
        return feats

    def fit(self, lines: list[dict], allow_train: bool = True) -> bool:
        """Fit (or reuse) the model. Returns True when a model is ready.

        Training is the only expensive step in building the analytics, and it depends solely on the set of
        completed orders. The trained models are therefore cached - in memory and in the database, so they
        survive restarts - under a fingerprint of the exact training data, and reused until that data changes.
        With allow_train=False only a cache hit is accepted (used to keep page loads instant)."""
        train = []
        for ln in lines:
            od, dd = ln["dates"].get("order_date"), ln["dates"].get("despatch_date")
            if ln["status"] == "completed" and od and dd:
                days = (dd - od).days
                if 0 <= days <= 365:
                    train.append((ln, days))
        self.ready = False
        if len(train) < 40:
            self.metrics = {"trained": False, "reason": f"only {len(train)} completed orders with dates"}
            return
        self.vocab = {}
        for role in CAT_ROLES:
            vals = sorted({str(ln["canon"].get(role) or ln["roles"].get(role)) for ln, _ in train
                           if (ln["canon"].get(role) or ln["roles"].get(role)) not in (None, "")})
            self.vocab[role] = {v: i for i, v in enumerate(vals)}
        X = np.array([self._row(ln) for ln, _ in train], dtype=float)
        y = np.array([d for _, d in train], dtype=float)
        cat_mask = [True] * len(CAT_ROLES) + [False] * 5
        X[:, :len(CAT_ROLES)] = np.where(X[:, :len(CAT_ROLES)] < 0, np.nan, X[:, :len(CAT_ROLES)])
        X[:, len(CAT_ROLES) + 1] = np.where(X[:, len(CAT_ROLES) + 1] < 0, np.nan, X[:, len(CAT_ROLES) + 1])
        self.cat_mask = cat_mask
        fingerprint = _fingerprint(X, y, self.vocab)
        cached = _load_cached(fingerprint)
        if cached:
            self.model, self.model_p80, self.metrics = cached
            self.ready = True
            return True
        if not allow_train:
            self.metrics = {"trained": False, "reason": "training in the background"}
            return False
        base = dict(categorical_features=cat_mask, max_iter=250, learning_rate=0.06, max_leaf_nodes=24,
                    min_samples_leaf=12, l2_regularization=0.1, random_state=7)
        cv = KFold(3, shuffle=True, random_state=1)
        pred = cross_val_predict(HistGradientBoostingRegressor(loss="absolute_error", **base), X, y, cv=cv)
        mae = float(np.mean(np.abs(pred - y)))
        baseline = float(np.mean(np.abs(np.median(y) - y)))
        self.model = HistGradientBoostingRegressor(loss="absolute_error", **base).fit(X, y)
        self.model_p80 = HistGradientBoostingRegressor(loss="quantile", quantile=0.8, **base).fit(X, y)
        self.ready = True
        self.metrics = {"trained": True, "algorithm": "Histogram gradient boosting (MAE loss) + P80 quantile model",
                        "samples": len(train), "cv_mae_days": round(mae, 1), "baseline_mae_days": round(baseline, 1),
                        "improvement_pct": round(100 * (1 - mae / baseline), 1) if baseline else None,
                        "median_lead_days": float(np.median(y))}
        _store_cached(fingerprint, self.model, self.model_p80, self.metrics)
        return True

    def predict(self, lines: list[dict]) -> None:
        if not self.ready:
            return
        todo = [ln for ln in lines if ln["status"] != "completed" and ln["dates"].get("order_date")]
        if not todo:
            return
        X = np.array([self._row(ln) for ln in todo], dtype=float)
        k = len(CAT_ROLES)
        X[:, :k] = np.where(X[:, :k] < 0, np.nan, X[:, :k])
        X[:, k + 1] = np.where(X[:, k + 1] < 0, np.nan, X[:, k + 1])
        p50, p80 = self.model.predict(X), self.model_p80.predict(X)
        today = date.today()
        for ln, a, b in zip(todo, p50, p80):
            od = ln["dates"]["order_date"]
            eta = od + timedelta(days=int(round(max(a, 0))))
            eta80 = od + timedelta(days=int(round(max(b, a, 0))))
            if eta < today:       # already past the typical lead time: project forward
                eta = today + timedelta(days=max(1, int(round((b - a) / 2)) or 1))
                eta80 = max(eta80, eta)
            due = ln["dates"].get("due_date")
            risk = "high" if due and eta > due else "medium" if due and eta80 > due else "low"
            ln["eta"] = {"expected": eta.isoformat(), "p80": eta80.isoformat(), "late_risk": risk,
                         "expected_lead_days": int(round(a))}


# ----------------------------------------------------------------------------- model cache
_MODEL_VERSION = "eta-v2"
_memory: dict[str, tuple] = {}


def _fingerprint(X: np.ndarray, y: np.ndarray, vocab: dict) -> str:
    import hashlib
    import json
    import sklearn
    h = hashlib.sha256(np.ascontiguousarray(X).tobytes())
    h.update(np.ascontiguousarray(y).tobytes())
    h.update(json.dumps(vocab, sort_keys=True).encode())
    h.update(f"{_MODEL_VERSION}|{sklearn.__version__}".encode())
    return h.hexdigest()


def _load_cached(fp: str):
    if fp in _memory:
        return _memory[fp]
    try:
        import base64
        import io
        import joblib
        from ..db import SessionLocal, get_setting
        with SessionLocal() as db:
            row = get_setting(db, "eta_model_cache")
        if row and row.get("fingerprint") == fp:
            model, p80 = joblib.load(io.BytesIO(base64.b64decode(row["blob"])))
            _memory.clear()
            _memory[fp] = (model, p80, row["metrics"])
            return _memory[fp]
    except Exception:  # noqa: BLE001 - a broken cache only means retraining
        return None
    return None


def _store_cached(fp: str, model, p80, metrics: dict) -> None:
    _memory.clear()
    _memory[fp] = (model, p80, metrics)
    try:
        import base64
        import io
        import joblib
        from ..db import SessionLocal, set_setting
        buf = io.BytesIO()
        joblib.dump((model, p80), buf, compress=3)
        with SessionLocal() as db:
            set_setting(db, "eta_model_cache", {"fingerprint": fp, "metrics": metrics,
                                                "blob": base64.b64encode(buf.getvalue()).decode()})
    except Exception:  # noqa: BLE001
        pass
