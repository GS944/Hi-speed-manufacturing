"""Categorical value canonicalisation.

"HI-SPEED SPARES", "Hi-Speed Spares" and "HI SPEED SPARES " are the same category. Values are
first bucketed by a normalised key, then near-duplicates (token-sort similarity >= threshold) are
merged with a union-find (disjoint-set) structure. Each cluster is named after its most frequent
spelling.
"""
from __future__ import annotations

import re
from collections import Counter

from rapidfuzz import fuzz


class DisjointSet:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]   # path halving
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def canonical_map(values, threshold: int = 92) -> dict[str, str]:
    """Return {raw value -> canonical display value}."""
    counts = Counter(str(v).strip() for v in values if v not in (None, ""))
    if not counts:
        return {}
    keys: dict[str, list[str]] = {}
    for v in counts:
        keys.setdefault(_key(v), []).append(v)
    groups = list(keys.values())
    names = [max(g, key=lambda x: counts[x]) for g in groups]
    ds = DisjointSet(len(groups))
    if len(groups) <= 400:  # O(n^2) pairwise pass is cheap for categorical columns
        normed = [re.sub(r"[^a-z0-9 ]+", " ", n.lower()) for n in names]
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if fuzz.token_sort_ratio(normed[i], normed[j]) >= threshold:
                    ds.union(i, j)
    clusters: dict[int, list[str]] = {}
    for i, g in enumerate(groups):
        clusters.setdefault(ds.find(i), []).extend(g)
    out = {}
    for members in clusters.values():
        best = max(members, key=lambda x: (counts[x], x != x.upper()))
        for m in members:
            out[m] = best
    return out
