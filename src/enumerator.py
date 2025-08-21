# src/enumerator.py
from __future__ import annotations
from typing import List, Dict, Set, Tuple
from .engine import ReachabilityEngine

def _run(protocol: str, n: int, max_depth: int = 10, parallel: bool = False, **kwargs):
    eng = ReachabilityEngine(protocol)
    if parallel:
        return eng.bfs_parallel(
            n,
            max_depth=max_depth,
            workers=kwargs.get("workers", 4),
            batch_size=kwargs.get("batch_size", 256),
            verbose=kwargs.get("verbose", False),
        )
    else:
        return eng.bfs(n, max_depth=max_depth)

def count_reachable(protocol: str, n: int, max_depth: int = 10, parallel: bool = False, **kwargs) -> int:
    """返回可达等价类总数（含深度0）。"""
    return _run(protocol, n, max_depth, parallel, **kwargs)["reachable_count"]

def per_level_counts(protocol: str, n: int, max_depth: int = 10, parallel: bool = False, **kwargs) -> List[int]:
    """返回每一层的状态数（从0层开始的连续列表）。"""
    res = _run(protocol, n, max_depth, parallel, **kwargs)
    layers = res.get("layers", {})
    if not layers:
        return [0]
    dmax = max(layers.keys())
    return [len(layers.get(d, set())) for d in range(0, dmax + 1)]

