from __future__ import annotations
from dataclasses import dataclass
from typing import FrozenSet, Tuple, List

Agent = str
Secret = str
Call = Tuple[Agent, Agent]  # (caller, callee)


@dataclass(frozen=True)
class Distribution:
    agents: Tuple[Agent, ...]                # fixed order
    secrets: Tuple[FrozenSet[Secret], ...]   # aligned with agents

    # ---------- basic ops ----------
    def apply_call(self, call: Call) -> "Distribution":
        a, b = call
        ia, ib = self.agents.index(a), self.agents.index(b)
        sa, sb = self.secrets[ia], self.secrets[ib]
        united = sa | sb
        secrets_new = list(self.secrets)
        secrets_new[ia] = united
        secrets_new[ib] = united
        return Distribution(self.agents, tuple(secrets_new))

    def is_final(self) -> bool:
        all_s = set().union(*self.secrets)
        return all(all_s == s for s in self.secrets)

    # canonical handled in canonical.py; here keep simple tuple
    def to_tuple(self):
        return tuple(tuple(sorted(s)) for s in self.secrets)

    @staticmethod
    def initial(n: int) -> "Distribution":
        agents = tuple(chr(ord("a") + i) for i in range(n))
        secrets = tuple(frozenset({ag.upper()}) for ag in agents)
        return Distribution(agents, secrets)


@dataclass(frozen=True)
class ProtocolState:
    distribution: Distribution
    tokens: FrozenSet[Agent]             # for TOK/SPI
    called_pairs: FrozenSet[frozenset]   # CO 已呼叫过的无序对

    def update(self, call: Call, protocol: str) -> "ProtocolState":
        a, b = call
        dist2 = self.distribution.apply_call(call)
        tokens = set(self.tokens)

        if protocol == "TOK":
            # caller将自己全部token交给callee（合并）
            if a in tokens:
                tokens.remove(a)
                tokens.add(b)
        elif protocol == "SPI":
            # callee永久失去token
            tokens.discard(b)

        new_pairs = set(self.called_pairs)
        new_pairs.add(frozenset({a, b}))

        return ProtocolState(
            dist2,
            frozenset(tokens),
            frozenset(new_pairs),
        )

    @staticmethod
    def initial(dist: Distribution, protocol: str) -> "ProtocolState":
        agents = dist.agents
        tokens = frozenset(agents) if protocol in {"TOK", "SPI"} else frozenset()
        return ProtocolState(dist, tokens, frozenset())
