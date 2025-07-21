# src/model.py
from __future__ import annotations
from dataclasses import dataclass
from typing import FrozenSet, Tuple, List

Agent = str
Secret = str
Call = Tuple[Agent, Agent]  # ordered (caller, callee)

@dataclass(frozen=True)
class Distribution:
    """
    Ordered distribution of secrets. agents[i] holds exactly secrets[i].
    Invariants:
      - len(agents) == len(secrets)
      - secrets[i] subset of ALL secrets
    """
    agents: Tuple[Agent, ...]
    secrets: Tuple[FrozenSet[Secret], ...]

    def apply_call(self, call: Call) -> "Distribution":
        a, b = call
        idx_a = self.agents.index(a)
        idx_b = self.agents.index(b)
        sa = self.secrets[idx_a]
        sb = self.secrets[idx_b]
        united = sa | sb
        secrets_new = list(self.secrets)
        secrets_new[idx_a] = united
        secrets_new[idx_b] = united
        return Distribution(self.agents, tuple(secrets_new))

    def is_final(self) -> bool:
        all_secrets = set().union(*self.secrets)
        return all(all_secrets == s for s in self.secrets)

    def to_tuple(self):
        """Canonical immutable form for hashing / set membership."""
        return tuple(tuple(sorted(s)) for s in self.secrets)

    @staticmethod
    def initial(n: int) -> "Distribution":
        agents = tuple(chr(ord('a') + i) for i in range(n))
        secrets = tuple(frozenset({agent.upper()}) for agent in agents)
        return Distribution(agents, secrets)

@dataclass(frozen=True)
class ProtocolState:
    """Holds extra metadata needed by a protocol (e.g. tokens, call history)."""
    distribution: Distribution
    tokens: FrozenSet[Agent]             # for TOK / SPI / future ATK
    called_pairs: FrozenSet[frozenset]   # unordered pairs that have spoken (CO)
    last_role: Tuple[Tuple[Agent, str], ...]  # (agent, 'caller'/'callee'/'none')
    # could extend with: received_flag, etc.

    def update(self, call: Call, protocol: str) -> "ProtocolState":
        a, b = call
        dist2 = self.distribution.apply_call(call)
        tokens = set(self.tokens)
        last_role_map = dict(self.last_role)

        if protocol == "TOK":
            # caller gives ALL its tokens to callee -> unify
            if a in tokens:
                tokens.discard(a)
                tokens.add(b)
        elif protocol == "SPI":
            # callee loses token permanently
            if b in tokens:
                tokens.discard(b)

        # Update last role
        last_role_map[a] = "caller"
        last_role_map[b] = "callee"

        # CO: record unordered pair
        new_pairs = set(self.called_pairs)
        new_pairs.add(frozenset({a, b}))

        return ProtocolState(
            dist2,
            frozenset(tokens),
            frozenset(new_pairs),
            tuple(sorted(last_role_map.items()))
        )

    @staticmethod
    def initial(distribution: Distribution, protocol: str) -> "ProtocolState":
        agents = distribution.agents
        if protocol in {"TOK", "SPI"}:
            tokens = frozenset(agents)  # everyone starts with a token
        else:
            tokens = frozenset()
        last_role = tuple((a, "none") for a in agents)
        return ProtocolState(
            distribution,
            tokens,
            frozenset(),
            last_role
        )
