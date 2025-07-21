"""
canonical.py
A canonical-key function that factors out ALL agent renamings.
For n ≤ 9 (our project scope) the naive factorial search is fine.
"""

from __future__ import annotations
import itertools
from typing import Tuple, FrozenSet, List


def _to_int_sets(secret_sets: Tuple[FrozenSet[str], ...]) -> List[set[int]]:
    # 'A'->0, 'B'->1, …
    return [set(ord(ch) - 65 for ch in S) for S in secret_sets]


def canonical_key(secret_sets: Tuple[FrozenSet[str], ...]) -> Tuple[Tuple[int, ...], ...]:
    """
    Return a permutation‑invariant key:
      • enumerate ALL n! bijections σ on {0..n-1}
      • apply σ to both agents AND secrets
      • choose lexicographically minimal tuple of tuple(int)
    Works for n ≤ 9 comfortably (9! = 362880).
    """
    int_sets = _to_int_sets(secret_sets)
    n = len(int_sets)
    best: Tuple[Tuple[int, ...], ...] | None = None

    for perm in itertools.permutations(range(n)):          # σ
        # σ acts on agents (rows) and on secret indices (elements)
        transformed: List[Tuple[int, ...]] = [
            tuple(sorted(perm[s] for s in int_sets[i]))     # σ(S_i)
            for i in range(n)
        ]
        # Reorder rows to standard order 0..n-1 via perm inverse
        inverse_rows = [0] * n
        for old, new in enumerate(perm):
            inverse_rows[new] = transformed[old]
        key = tuple(inverse_rows)

        if best is None or key < best:
            best = key

    # best is never None because permutations list non‑empty
    return best  # type: ignore
