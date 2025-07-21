# src/metrics.py
"""
Collection of analysis helpers:
  • avg_branching         — average branching factor from BFS stats
  • random_run / expected_length — Monte‑Carlo expected call length
"""

from statistics import mean
from statistics import stdev
from typing import List, Dict
import random

# ---------- already existing helper ----------
def avg_branching(transitions: int, visited: int) -> float:
    """Rough branching factor: total explored edges / visited nodes."""
    return transitions / visited if visited else 0.0


# ---------- NEW: Monte‑Carlo simulation ----------
from .engine import ReachabilityEngine
from .protocols import permitted_calls
from .model import Distribution, ProtocolState
from tqdm import trange    



def random_run(protocol: str, n: int, max_steps: int = 1000) -> int:
    """
    Perform ONE random legal call sequence until all agents are experts
    or max_steps reached. Return number of calls used.
    """
    dist = Distribution.initial(n)
    state = ProtocolState.initial(dist, protocol)

    for step in range(max_steps):
        if state.distribution.is_final():
            return step
        calls = permitted_calls(state, protocol)
        if not calls:                 # dead end (should not occur for ANY/TOK)
            return step
        state = state.update(random.choice(calls), protocol)
    return max_steps


def expected_length(protocol: str, n: int, runs: int = 10_000):
    random.seed(42)                                   # 保证可复现
    lengths = [random_run(protocol, n)
               for _ in trange(runs, desc=f"{protocol}{n}")]
    mu = sum(lengths) / runs
    sigma = stdev(lengths)
    return mu, sigma


# Quick sanity‐check (executes only when run as script)
if __name__ == "__main__":
    for p in ["ANY", "TOK", "CO"]:
        print(f"n=5  {p:3}  E[length] ≈ {expected_length(p, 5, runs=1000):.2f}")
