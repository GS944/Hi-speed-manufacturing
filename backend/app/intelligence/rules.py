"""Tiny interpreter for the JSON rule language used by stage and completion rules.

  {"present": role}                 {"empty": role}
  {"gt"|"gte"|"lt"|"lte"|"eq": [a, b]}   - a/b are role names or literals
  {"any": [rule, ...]}  {"all": [rule, ...]}  {"not": rule}
"""
from __future__ import annotations

from typing import Any, Callable

Getter = Callable[[str], Any]


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _operand(x, get: Getter):
    return _num(get(x)) if isinstance(x, str) else _num(x)


def evaluate(rule: dict, get: Getter) -> bool:
    if not rule:
        return False
    (op, arg), = rule.items()
    if op == "present":
        v = get(arg)
        return v is not None and v != ""
    if op == "empty":
        v = get(arg)
        return v is None or v == ""
    if op == "any":
        return any(evaluate(r, get) for r in arg)
    if op == "all":
        return all(evaluate(r, get) for r in arg)
    if op == "not":
        return not evaluate(arg, get)
    a, b = (_operand(x, get) for x in arg)
    if a is None or b is None:
        return False
    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b, "eq": a == b}[op]
