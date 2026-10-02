"""Feature extraction for a spreadsheet column: header text + value distribution.

The vector is a concatenation of
  * hashed character n-grams of the header (robust to typos / abbreviations: "Qty", "QTY.", "Quantity")
  * hashed word tokens of the header
  * hashed character n-grams of a sample of the cell values (learns vocabularies such as EN-19, H13)
  * hashed character n-grams of the values' *shape* (digits->9, letters->a/A) - learns formats
  * 20 numeric statistics of the value distribution (types, uniqueness, magnitudes, monotonicity...)
"""
from __future__ import annotations

import math
import re
from datetime import datetime

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import HashingVectorizer

N_HDR_CHAR, N_HDR_WORD, N_VAL, N_SHAPE = 2048, 512, 1024, 512

_hdr_char = HashingVectorizer(analyzer="char_wb", ngram_range=(2, 4), n_features=N_HDR_CHAR, alternate_sign=False, norm="l2")
_hdr_word = HashingVectorizer(analyzer="word", token_pattern=r"[a-z0-9#]+", n_features=N_HDR_WORD, alternate_sign=False, norm="l2")
_val_char = HashingVectorizer(analyzer="char_wb", ngram_range=(2, 4), n_features=N_VAL, alternate_sign=False, norm="l2")
_shape_char = HashingVectorizer(analyzer="char", ngram_range=(2, 4), n_features=N_SHAPE, alternate_sign=False, norm="l2")

_GENERIC = re.compile(r"^(column|unnamed|field|col)\s*[:#]?\s*[a-z]{0,3}\s*\d*(\s*\(\d+\))?$")
_HRC = re.compile(r"^\d{2}\s*-\s*\d{2}(\s*hrc)?$", re.I)


def normalize_header(h: str | None) -> str:
    h = (h or "").lower()
    h = re.sub(r"\(\d+\)$", "", h)
    h = h.replace("n0", "no").replace("_", " ")
    h = re.sub(r"[^a-z0-9#/&% ]+", " ", h)
    h = re.sub(r"\s+", " ", h).strip()
    return "" if _GENERIC.match(h) else h


def _shape(s: str) -> str:
    s = re.sub(r"[0-9]+", "9", s)
    s = re.sub(r"[a-z]+", "a", s)
    return re.sub(r"[A-Z]+", "A", s)


def value_text(values: list) -> tuple[str, str]:
    seen, sample = set(), []
    for v in values:
        if v is None or v == "":
            continue
        s = v.strftime("%Y-%m-%d") if isinstance(v, datetime) else str(v)
        if s not in seen:
            seen.add(s)
            sample.append(s)
        if len(sample) >= 40:
            break
    return " | ".join(x.lower() for x in sample), " | ".join(_shape(x) for x in sample)


_PAIR = re.compile(r"^(\d{1,3})\s*-\s*(\d{1,3})")


def _range_spread(strs: list[str]) -> float:
    """Mean width of 'a-b' ranges: specs (42-46) are wide, measurements (43-44) are narrow."""
    spreads = [abs(int(b) - int(a)) for a, b in (m.groups() for m in map(_PAIR.match, strs) if m)]
    return min(np.mean(spreads), 10) / 5 if spreads else 0.0


_NUMSTR = re.compile(r"^-?\d+(\.\d+)?$")


def coerce(values: list) -> list:
    """Type normalisation before featurising: numeric strings ("2475", "12.5") become numbers."""
    out = []
    for v in values:
        if isinstance(v, str) and _NUMSTR.match(v.strip()):
            f = float(v)
            out.append(int(f) if f.is_integer() else f)
        else:
            out.append(v)
    return out


def value_stats(values: list) -> np.ndarray:
    n = len(values) or 1
    vals = [v for v in values if v is not None and v != ""]
    m = len(vals) or 1
    nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    ints = [v for v in nums if isinstance(v, int) or float(v).is_integer()]
    dates = [v for v in vals if isinstance(v, datetime)]
    strs = [str(v) for v in vals if isinstance(v, str)]
    lens = [len(str(v)) for v in vals] or [0]
    distinct = len({str(v) for v in vals})
    mono = 0.0
    if len(ints) >= 3:
        diffs = [b - a for a, b in zip(ints, ints[1:])]
        mono = sum(1 for d in diffs if d == 1) / len(diffs)
    med = float(np.median([abs(x) for x in nums])) if nums else 0.0
    frac_dec = (len(nums) - len(ints)) / m
    feats = [
        1 - len(vals) / n,                               # emptiness
        len(nums) / m, len(ints) / m, len(dates) / m, len(strs) / m,
        distinct / m,                                    # uniqueness
        math.log1p(np.mean(lens)) / 4, math.log1p(np.std(lens)) / 4,
        sum(bool(re.search(r"\d", s)) and bool(re.search(r"[A-Za-z]", s)) for s in strs) / m,
        sum(s.replace(" ", "").isalpha() for s in strs) / m,
        sum(bool(_HRC.match(s)) for s in strs) / m,
        math.log1p(med) / 12,
        sum(1 for x in nums if x == 0) / m,
        mono,
        sum(s.isupper() for s in strs) / m,
        math.log1p(distinct) / 8,
        sum("/" in s for s in strs) / m,
        frac_dec,
        sum(len(s) > 25 for s in strs) / m,
        sum(bool(re.search(r"\d{5,}", s)) for s in strs) / m,
        _range_spread(strs),
    ]
    return np.asarray(feats, dtype=np.float32)


N_STATS = 21


def featurize(columns: list[tuple[str | None, list]]) -> sparse.csr_matrix:
    """columns: list of (header, values)."""
    columns = [(h, coerce(v)) for h, v in columns]
    headers = [normalize_header(h) for h, _ in columns]
    vtexts = [value_text(v) for _, v in columns]
    blocks = [
        _hdr_char.transform(headers) * 1.6,
        _hdr_word.transform(headers),
        _val_char.transform([a for a, _ in vtexts]),
        _shape_char.transform([b for _, b in vtexts]) * 0.7,
        sparse.csr_matrix(np.vstack([value_stats(v) for _, v in columns]) * 1.5),
    ]
    return sparse.hstack(blocks, format="csr", dtype=np.float32)
