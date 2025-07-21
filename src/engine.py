# src/engine.py
from __future__ import annotations
from collections import deque
from typing import Set, Dict, Tuple, List
from .model import Distribution, ProtocolState
from .protocols import permitted_calls

class ReachabilityEngine:
    def __init__(self, protocol: str):
        self.protocol = protocol

    def bfs(self, n: int, max_depth: int = 10):
        """Breadth-first enumeration of distributions reachable up to depth."""
        start = Distribution.initial(n)
        root = ProtocolState.initial(start, self.protocol)
        seen_dist = {start.to_tuple()}
        queue = deque([(root, 0)])
        layers = {0: {start.to_tuple()}}
        transitions = 0

        while queue:
            state, depth = queue.popleft()
            if depth == max_depth:
                continue
            for call in permitted_calls(state, self.protocol):
                new_state = state.update(call, self.protocol)
                dist_key = new_state.distribution.to_tuple()
                transitions += 1
                if dist_key not in seen_dist:
                    seen_dist.add(dist_key)
                    queue.append((new_state, depth + 1))
                    layers.setdefault(depth + 1, set()).add(dist_key)
        return {
            "reachable_count": len(seen_dist),
            "layers": layers,
            "transitions": transitions
        }
