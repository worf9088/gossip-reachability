# src/engine.py
from __future__ import annotations
from collections import deque
from typing import Dict, Set, Tuple

from .model import Distribution, ProtocolState
from .protocols import permitted_calls
from .canonical import canonical_key


class ReachabilityEngine:
    """Breadth‑first enumeration of reachable secret distributions."""

    def __init__(self, protocol: str):
        assert protocol in {"ANY", "CO", "LNS", "TOK", "SPI"}
        self.protocol = protocol

    def bfs(self, n: int, max_depth: int = 10):
        """
        Enumerate all canonical distributions reachable within `max_depth`
        synchronous calls (depth = call sequence length).

        Returns:
            {
                "reachable_count": int,      # unique canonical states
                "layers": Dict[int, Set[key]],
                "transitions": int           # explored edges
            }
        """
        # ---------- initial state ----------
        start_dist = Distribution.initial(n)
        root_state = ProtocolState.initial(start_dist, self.protocol)

        start_key = canonical_key(start_dist.secrets)
        seen: Set[Tuple[str, ...]] = {start_key}
        layers: Dict[int, Set[Tuple[str, ...]]] = {0: {start_key}}
        queue = deque([(root_state, 0)])
        transitions = 0

        # ---------- BFS ----------
        while queue:
            state, depth = queue.popleft()
            if depth == max_depth:
                continue

            for call in permitted_calls(state, self.protocol):
                new_state = state.update(call, self.protocol)
                key = canonical_key(new_state.distribution.secrets)
                transitions += 1

                if key not in seen:
                    seen.add(key)
                    queue.append((new_state, depth + 1))
                    layers.setdefault(depth + 1, set()).add(key)

        return {
            "reachable_count": len(seen),
            "layers": layers,
            "transitions": transitions,
        }
