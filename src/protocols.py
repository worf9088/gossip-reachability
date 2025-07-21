# src/protocols.py
from __future__ import annotations
from typing import Iterable, List, Tuple
from .model import ProtocolState, Agent, Call

def possible_calls(state: ProtocolState) -> Iterable[Call]:
    agents = state.distribution.agents
    for a in agents:
        for b in agents:
            if a != b:
                yield (a, b)

def allow_ANY(state: ProtocolState, call: Call) -> bool:
    return True

def allow_CO(state: ProtocolState, call: Call) -> bool:
    a, b = call
    return frozenset({a, b}) not in state.called_pairs

def allow_LNS(state: ProtocolState, call: Call) -> bool:
    # caller must learn at least one new secret
    a, b = call
    dist = state.distribution
    sa = dist.secrets[dist.agents.index(a)]
    sb = dist.secrets[dist.agents.index(b)]
    return not sb.issubset(sa)  # caller gains something

def allow_TOK(state: ProtocolState, call: Call) -> bool:
    # caller must have a token (in our interpretation)
    a, _ = call
    return a in state.tokens

def allow_SPI(state: ProtocolState, call: Call) -> bool:
    # caller must still possess token (never lost it by being called)
    a, _ = call
    return a in state.tokens

ALLOW_MAP = {
    "ANY": allow_ANY,
    "CO": allow_CO,
    "LNS": allow_LNS,
    "TOK": allow_TOK,
    "SPI": allow_SPI
}

def permitted_calls(state: ProtocolState, protocol: str) -> List[Call]:
    f = ALLOW_MAP[protocol]
    return [c for c in possible_calls(state) if f(state, c)]
