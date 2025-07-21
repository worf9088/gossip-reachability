# src/enumerator.py
from __future__ import annotations
from typing import Dict
from .engine import ReachabilityEngine

def count_reachable(protocol: str, n: int, depth: int = 10) -> int:
    eng = ReachabilityEngine(protocol)
    res = eng.bfs(n, depth)
    return res["reachable_count"]

def table_counts(n_values=(2,3,4), depth=10):
    table: Dict[int, Dict[str, int]] = {}
    for n in n_values:
        table[n] = {}
        for p in ["LNS", "CO", "SPI", "TOK", "ANY"]:
            table[n][p] = count_reachable(p, n, depth)
    return table

if __name__ == "__main__":
    print(table_counts())
