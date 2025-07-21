from __future__ import annotations
from typing import Dict
from .engine import ReachabilityEngine


def count_reachable(protocol: str, n: int, depth=10) -> int:
    eng = ReachabilityEngine(protocol)
    return eng.bfs(n, depth)["reachable_count"]


def table_counts(n_values=(2, 3, 4), depth=10):
    tbl: Dict[int, Dict[str, int]] = {}
    for n in n_values:
        tbl[n] = {}
        for proto in ["LNS", "CO", "SPI", "TOK", "ANY"]:
            tbl[n][proto] = count_reachable(proto, n, depth)
    return tbl


if __name__ == "__main__":
    print(table_counts())
