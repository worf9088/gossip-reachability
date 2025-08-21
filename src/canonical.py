# src/canonical.py
from __future__ import annotations
import itertools
from functools import lru_cache
from typing import Tuple, FrozenSet

@lru_cache(maxsize=None)
def _perms(n: int):
    return tuple(itertools.permutations(range(n)))

@lru_cache(maxsize=None)
def canonical_key(secret_sets: Tuple[FrozenSet[str], ...]) -> Tuple[Tuple[int, ...], ...]:
    int_sets = [set(ord(ch) - 65 for ch in S) for S in secret_sets]
    n = len(int_sets)
    best = None
    for perm in _perms(n):
        transformed = [tuple(sorted(perm[s] for s in int_sets[i])) for i in range(n)]
        inv = [()] * n
        for old, new in enumerate(perm):
            inv[new] = transformed[old]
        key = tuple(inv)
        if best is None or key < best:
            best = key
    return best  # type: ignore
