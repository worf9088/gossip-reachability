from __future__ import annotations
from typing import List, Iterable, Tuple
from .model import ProtocolState, Call


def _all_calls(agents: Tuple[str, ...]) -> Iterable[Call]:
    for a in agents:
        for b in agents:
            if a != b:
                yield (a, b)


# ---------- per‑protocol permission ----------
def allow_ANY(state: ProtocolState, call: Call) -> bool:
    return True


def allow_CO(state: ProtocolState, call: Call) -> bool:
    return frozenset(call) not in state.called_pairs


def allow_LNS(state: ProtocolState, call: Call) -> bool:
    a, b = call

    if frozenset({a, b}) in state.called_pairs:
        return False
    
    dist = state.distribution
    sa = dist.secrets[dist.agents.index(a)]
    sb = dist.secrets[dist.agents.index(b)]
    return not sb.issubset(sa)


def allow_TOK(state: ProtocolState, call: Call) -> bool:
    a, _ = call
    return a in state.tokens


def allow_SPI(state: ProtocolState, call: Call) -> bool:
    a, _ = call
    return a in state.tokens


ALLOW = {
    "ANY": allow_ANY,
    "CO": allow_CO,
    "LNS": allow_LNS,
    "TOK": allow_TOK,
    "SPI": allow_SPI,
}


def permitted_calls(state: ProtocolState, protocol: str) -> List[Call]:
    pred = ALLOW[protocol]
    return [c for c in _all_calls(state.distribution.agents) if pred(state, c)]
