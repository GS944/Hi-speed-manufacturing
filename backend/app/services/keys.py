"""Key normalisation and multi-reference parsing."""
from __future__ import annotations

import re
from datetime import date, datetime

_SPLIT = re.compile(r"\s*(?:/|,|&|\+|;|\band\b)\s*", re.I)


def norm_key(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, float):
        v = int(v) if v.is_integer() else v
    s = str(v).strip().upper()
    s = re.sub(r"\s+", " ", s)
    if re.fullmatch(r"\d+(\.0+)?", s):
        s = str(int(float(s)))
    return s or None


def parse_refs(v) -> list[str]:
    """'2328/29' -> ['2328','2329'];  '2445/46' -> ['2445','2446'];  '1201-1203' -> 3 keys;
    '4006' -> ['4006'];  'LOI' -> ['LOI']."""
    k = norm_key(v)
    if not k:
        return []
    m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", k)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if len(m.group(2)) < len(m.group(1)):
            b = int(m.group(1)[: len(m.group(1)) - len(m.group(2))] + m.group(2))
        if 0 < b - a <= 30:
            return [str(x) for x in range(a, b + 1)]
    parts = [p for p in _SPLIT.split(k) if p]
    if len(parts) == 1:
        return [norm_key(parts[0])]
    out, first = [], None
    for p in parts:
        p = p.strip("[]() ")
        if re.fullmatch(r"\d+", p):
            if first and len(p) < len(first):
                p = first[: len(first) - len(p)] + p
            first = first or p
        nk = norm_key(p)
        if nk and nk not in out:
            out.append(nk)
    return out


def to_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:      # excel serial
        from datetime import timedelta
        return date(1899, 12, 30) + timedelta(days=int(v))
    if isinstance(v, str):
        s = v.strip()
        try:
            return datetime.fromisoformat(s).date()
        except ValueError:
            pass
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    return None


def to_num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None
