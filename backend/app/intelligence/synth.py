"""Synthetic training-column generator.

For every semantic role in the ontology we synthesise many plausible columns (a header variant plus
a list of cell values drawn from the role's value-distribution family). Header variants are produced
by augmentation (case, punctuation, abbreviations, typos, numbering) and ~25% of samples get a
meaningless header ("Column F", "Unnamed: 3") so the network also learns to recognise a column from
its values alone.
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta

_ABBR = [("quantity", "qty"), ("number", "no"), ("number", "num"), ("no", "#"), ("no", "n0"), ("date", "dt"),
         ("customer", "cust"), ("description", "desc"), ("despatch", "dispatch"), ("colour", "color"),
         ("issued", "issue"), ("value", "val"), ("operation", "opn"), ("material", "matl")]
_GENERIC = ["Column {L}", "Unnamed: {n}", "Column{n}", "Field {n}", "", "Col {L}"]

_WORDS = ["SRI", "SHREE", "GLOBE", "TECH", "RAPID", "KSHIPRA", "VINAYAKA", "MARUTHI", "LAKSHMI", "JYOTHI",
          "COASTAL", "ACCURATE", "UNIVERSAL", "BALAJI", "MITHILA", "ANANYA", "ZEAL", "HARI", "DEV", "MATHRU",
          "KANCHI", "DOLPHIN", "FUTURE", "UDAY", "IMTECH", "MIKRON", "INDURA", "CLASSIC", "TUNGALOY"]
_SUFFIX = ["ENGINEERING WORKS", "ENTERPRISES", "INDUSTRIES", "Industries Pvt. Ltd", "TOOLING SOLUTION",
           "GRINDERS", "HEAT TREATERS", "TOOLS", "Engineering Company", "PRECISION", "TECHNOLOGIES", "& Co"]
_ITEM_PFX = ["PCLNR", "PCLNL", "SCLCR", "SDJCL", "SVJBR", "S16Q", "S25T", "CTEL", "PSBNR", "MWLNR", "B-280SF1",
             "PUR-S16Q", "DDJNR", "SER", "TTER", "SNR", "BORING BAR", "TOOL HOLDER", "PRDCN", "S32U"]
_REMARKS = ["PRICE ACCEPTED", "DC CANCELLED", "1 NO REJECTED", "QTY CHANGED", "STOCK ITEM", "MATERIAL CHANGE",
            "only sent", "urgent", "partial", "rework done", "HT MISSING", "re-issued", "as per drawing"]
_CATS_FALLBACK = ["Alpha", "Beta", "Gamma", "Delta", "Standard", "Special", "Other", "A", "B", "C"]
_ADDR = ["No.{n}, {k}th main", "{k}th cross", "Peenya indl area", "Peenya {k}nd stage", "Bangalore - 5600{k}{k}",
         "Yeshwanthpur", "#{n}/{k}, {k}rd main", "Industrial suburb", "MES Road", "Near TVS cross", "Tumkur road"]


def _rand_header(rng: random.Random, base: str) -> str:
    h = base
    for long, short in _ABBR:
        if long in h and rng.random() < 0.35:
            h = h.replace(long, short)
    r = rng.random()
    if r < 0.3:
        h = h.upper()
    elif r < 0.6:
        h = h.title()
    if rng.random() < 0.25:
        h = h.replace(" ", rng.choice(["_", ".", "", " "]))
    if rng.random() < 0.15:
        h += rng.choice([".", ":", " -", " (nos)", " #"])
    if rng.random() < 0.08 and len(h) > 4:          # typo
        i = rng.randrange(1, len(h) - 1)
        h = h[:i] + h[i + 1:]
    return h


def _generic_header(rng: random.Random) -> str:
    return rng.choice(_GENERIC).format(L=rng.choice(string.ascii_uppercase), n=rng.randint(1, 40))


def _vary_case(rng, s: str) -> str:
    r = rng.random()
    return s.upper() if r < 0.25 else s.title() if r < 0.4 else s


def gen_values(kind: str, rng: random.Random, n: int, examples: list[str] | None = None) -> list:
    out: list = []
    empty_p = rng.choice([0, 0, 0.02, 0.1, 0.3])
    if kind == "int_seq":
        v = rng.randint(1, 6000)
        refs = rng.random() < 0.3          # reference columns: unordered, some multi-refs like "2328/29"
        for _ in range(n):
            if refs:
                x = rng.randint(1, 6000)
                out.append(f"{x}/{(x + 1) % 100:02d}" if rng.random() < 0.08 else x)
            else:
                out.append(v)
                v += 1 if rng.random() > 0.03 else rng.randint(2, 4)
        return out
    if kind == "remarks":
        return [rng.choice(_REMARKS) + (f" {rng.randint(1, 99)}" if rng.random() < .4 else "")
                if rng.random() < 0.15 else None for _ in range(n)]
    if kind == "int_code":
        codes = [rng.randint(1000, 9999)] if rng.random() < .1 else [rng.randint(2290, 2340) for _ in range(rng.randint(4, 20))]
    if kind == "category":
        pool = examples or _CATS_FALLBACK
        k = rng.randint(2, min(len(pool), 10))
        cats = [_vary_case(rng, c) for c in rng.sample(pool, k)]
        weights = [rng.random() ** 2 + 0.02 for _ in cats]
    if kind == "name":
        names = [f"{rng.choice(_WORDS)} {rng.choice(_WORDS) + ' ' if rng.random() < .4 else ''}{rng.choice(_SUFFIX)}"
                 for _ in range(rng.randint(3, 25))]
    base_date = datetime(2025, 4, 1) + timedelta(days=rng.randint(0, 500))
    sorted_dates = rng.random() < 0.6
    for i in range(n):
        if rng.random() < empty_p:
            out.append(None)
            continue
        if kind == "int_code":
            out.append(rng.choice(codes))
        elif kind == "date":
            d = base_date + timedelta(days=(i // rng.randint(1, 6)) if sorted_dates else rng.randint(0, 200))
            out.append(d)
        elif kind == "qty":
            out.append(max(1, int(rng.lognormvariate(2.4, 1.1))))
        elif kind == "qty_zero":
            out.append(0 if rng.random() < 0.8 else rng.randint(1, 12))
        elif kind == "money":
            v = rng.lognormvariate(3.6, 0.9)
            out.append(round(v, rng.choice([0, 1, 2])) if rng.random() < .6 else int(v))
        elif kind == "money_flat":
            out.append(rng.choice([1000, 1000, 1000, 500, 2000, 5000]) if rng.random() < .9 else round(rng.uniform(5, 200), 2))
        elif kind == "category":
            out.append(rng.choices(cats, weights)[0])
        elif kind == "text_item":
            s = f"{rng.choice(_ITEM_PFX)} {rng.randint(10, 40)}{rng.randint(10, 40)} {rng.choice('MKPSQRT')}{rng.randint(6, 25)}"
            if rng.random() < .5:
                s += f" - {rng.randint(1000000, 9999999)}"
            out.append(s)
        elif kind == "name":
            out.append(rng.choice(names))
        elif kind == "doc_ref":
            r = rng.random()
            out.append(rng.randint(100000, 999999) if r < .45 else rng.choice(["LOI", "VERBAL", "MAIL"]) if r < .55 else
                       f"{''.join(rng.choices(string.ascii_uppercase, k=3))}/{rng.randint(1, 999):03d}" if r < .8 else rng.randint(1000, 9999))
        elif kind == "hrc_range":
            a = rng.choice([40, 41, 42, 44, 50, 55])
            out.append(f"{a}-{a + rng.choice([3, 4, 4, 5, 6])}" + (" hrc" if rng.random() < .5 else ""))
        elif kind == "hrc_pair":
            a = rng.randint(40, 47)
            out.append(f"{a}-{a + rng.choice([-1, 0, 0, 1, 1, 2])}")
        elif kind == "invoice_text":
            r = rng.random()
            d = lambda: f"{rng.randint(1, 28)}/{rng.randint(1, 12)}/{rng.choice([25, 26])}"
            out.append(f"[{rng.randint(1, 120)}] {d()} // [{rng.randint(1, 50)}] {d()}" if r < .4 else
                       f"{rng.randint(26000000, 26999999)}" if r < .65 else f"BILL {rng.randint(1, 99)}" if r < .8 else None)
        elif kind == "weight":
            out.append(round(rng.uniform(0.03, 6), 2))
        elif kind == "tariff":
            out.append(rng.choice([998876, 998876, 84669310, 998898]))
        elif kind == "address":
            out.append(rng.choice(_ADDR).format(n=rng.randint(1, 400), k=rng.randint(1, 9)))
        elif kind == "gstin":
            out.append(f"29{''.join(rng.choices(string.ascii_uppercase, k=5))}{rng.randint(1000, 9999)}{rng.choice(string.ascii_uppercase)}1Z{rng.randint(1, 9)}"
                       if rng.random() < .7 else rng.randint(10 ** 10, 10 ** 11))
        elif kind == "phone":
            out.append(str(rng.randint(6 * 10 ** 9, 10 ** 10 - 1)))
        elif kind == "size":
            out.append(rng.choice([f"S{rng.randint(8, 50)}", str(rng.choice([1212, 1616, 2020, 2525, 3232, 4040])), f"R/{rng.randint(10, 40)}", rng.randint(16, 60)]))
        else:  # unknown / noise
            r = rng.random()
            out.append(rng.randint(0, 120) if r < .4 else ''.join(rng.choices(string.ascii_uppercase + string.digits, k=rng.randint(2, 8))) if r < .7 else None)
    return out


def generate(ontology: dict, per_role: int = 110, seed: int = 7) -> tuple[list[tuple[str, list]], list[str]]:
    rng = random.Random(seed)
    cols, labels = [], []
    for role, spec in ontology["roles"].items():
        headers = spec["headers"] + [spec["label"].lower()]
        for i in range(per_role):
            if i % 4 == 3:
                h = _generic_header(rng)
            else:
                h = _rand_header(rng, rng.choice(headers))
            vals = gen_values(spec["kind"], rng, rng.randint(8, 60), spec.get("examples"))
            cols.append((h, vals))
            labels.append(role)
    for i in range(per_role):            # explicit "unknown" class
        h = _generic_header(rng) if i % 2 else rng.choice(["misc", "x", "check", "flag2", "temp", "ref2", "extra", "aux"])
        cols.append((h, gen_values("unknown", rng, rng.randint(5, 40))))
        labels.append("unknown")
    return cols, labels
