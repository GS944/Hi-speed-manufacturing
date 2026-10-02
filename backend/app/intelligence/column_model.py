"""Neural column-role classifier (multi-layer perceptron) with feedback learning.

Training data = synthetic columns generated from the ontology  +  every correction the admin makes
in the mapping editor (stored as feedback and up-weighted). The model is retrained automatically
whenever the ontology or the feedback set changes; the trained network is cached on disk.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
from datetime import datetime
from pathlib import Path

import joblib
import sklearn
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

from ..config import MODELS_DIR
from . import synth
from .features import featurize

log = logging.getLogger("ordertrack.ml")
ONTOLOGY_PATH = Path(__file__).with_name("ontology.json")
LEGACY_FEEDBACK_PATH = MODELS_DIR / "column_feedback.json"
MODEL_PATH = MODELS_DIR / "column_mlp.joblib"

_lock = threading.RLock()
_model: dict | None = None


def load_ontology() -> dict:
    return json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))


def _enc(v):
    return {"$d": v.isoformat()} if isinstance(v, datetime) else v


def _dec(v):
    return datetime.fromisoformat(v["$d"]) if isinstance(v, dict) and "$d" in v else v


def load_feedback() -> list[dict]:
    """Admin corrections live in the database so they survive redeploys on hosts without a persistent disk."""
    from ..db import SessionLocal, get_setting, set_setting
    try:
        with SessionLocal() as db:
            fb = get_setting(db, "column_feedback")
            if fb is None and LEGACY_FEEDBACK_PATH.exists():      # one-time move from the old file location
                fb = json.loads(LEGACY_FEEDBACK_PATH.read_text(encoding="utf-8"))
                set_setting(db, "column_feedback", fb)
            return fb or []
    except Exception:  # noqa: BLE001 - database not initialised yet (e.g. build-time pre-training)
        return []


def add_feedback(examples: list[tuple[str, list, str]]) -> None:
    """examples: (header, values, role) confirmed/corrected by the admin."""
    from ..db import SessionLocal, set_setting
    with _lock:
        fb = load_feedback()
        index = {(e["header"], e["role"]): i for i, e in enumerate(fb)}
        for header, values, role in examples:
            item = {"header": header, "role": role, "values": [_enc(v) for v in values[:80]]}
            if (header, role) in index:
                fb[index[(header, role)]] = item
            else:
                fb.append(item)
        with SessionLocal() as db:
            set_setting(db, "column_feedback", json.loads(json.dumps(fb, default=str)))


def _signature(onto: dict, fb: list) -> str:
    h = hashlib.sha256(json.dumps(onto["roles"], sort_keys=True).encode())
    h.update(json.dumps(fb, sort_keys=True, default=str).encode())
    h.update(b"mlp-v5")
    h.update(sklearn.__version__.encode())
    return h.hexdigest()[:16]


def train(force: bool = False) -> dict:
    global _model
    with _lock:
        onto = load_ontology()
        fb = load_feedback()
        sig = _signature(onto, fb)
        if not force and _model and _model["signature"] == sig:
            return _model
        if not force and MODEL_PATH.exists():
            try:
                cached = joblib.load(MODEL_PATH)
            except Exception:  # noqa: BLE001 - incompatible pickle (library upgrade): retrain
                cached = {}
            if cached.get("signature") == sig:
                _model = cached
                return _model
        t0 = time.time()
        cols, labels = synth.generate(onto)
        rng = random.Random(11)
        for e in fb:                       # admin feedback, augmented by value subsampling
            vals = [_dec(v) for v in e["values"]]
            for _ in range(25):
                k = max(3, int(len(vals) * rng.uniform(0.4, 1.0)))
                cols.append((e["header"], rng.sample(vals, min(k, len(vals))) if vals else []))
                labels.append(e["role"])
        X = featurize(cols)
        classes = sorted(set(labels))
        y = np.array([classes.index(l) for l in labels])   # int labels (sklearn early-stopping needs numeric y)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.15, random_state=3, stratify=y)
        clf = MLPClassifier(hidden_layer_sizes=(256, 96), activation="relu", alpha=1e-4,
                            batch_size=128, learning_rate_init=2e-3, max_iter=60,
                            early_stopping=True, n_iter_no_change=6, random_state=5)
        clf.fit(Xtr, ytr)
        acc = float(clf.score(Xte, yte))
        clf.fit(X, y) if len(fb) else None   # final fit on everything when real feedback exists
        _model = {"signature": sig, "clf": clf, "classes": classes, "holdout_accuracy": acc,
                  "n_train": int(X.shape[0]), "n_feedback": len(fb), "trained_at": datetime.now().isoformat(timespec="seconds"),
                  "train_seconds": round(time.time() - t0, 1), "architecture": f"MLP {X.shape[1]}-256-96-{len(classes)} (ReLU, Adam)"}
        joblib.dump(_model, MODEL_PATH, compress=3)
        log.info("column classifier trained: acc=%.3f n=%d in %.1fs", acc, X.shape[0], time.time() - t0)
        return _model


def predict_proba(columns: list[tuple[str | None, list]]) -> tuple[np.ndarray, list[str]]:
    m = train()
    X = featurize(columns)
    return m["clf"].predict_proba(X), m["classes"]


def model_info() -> dict:
    m = train()
    return {k: v for k, v in m.items() if k != "clf"}


def pretrain() -> None:
    """Build-time training (e.g. Render build step) so a sleeping free instance wakes up fast."""
    logging.basicConfig(level=logging.INFO)
    info = train()
    print(f"column model ready: {info['architecture']}, hold-out accuracy {info['holdout_accuracy']:.3f}, saved to {MODEL_PATH}")


def warm_up_async() -> None:
    threading.Thread(target=train, daemon=True, name="column-model-train").start()


if __name__ == "__main__":
    pretrain()
