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

# === Keys-only 工厂方法 · 兼容补丁（覆盖版） =======================================
# 目的：让 engine 的 keys-only 模式可用，并确保 Distribution.secrets 的内部
#       元素是 set/frozenset（而不是 tuple），以支持 `|` 等集合运算。

from typing import Any, Iterable, Tuple, Type

def _to_canonical_tuple(key_like: Any) -> Tuple[Tuple[int, ...], ...]:
    """
    将任意可迭代的“二维整型序列”转换为 tuple[tuple[int]]，并做基本校验。
    例：[[0,1],[2]] -> ((0,1),(2,))
    """
    rows = []
    try:
        for row in key_like:
            if row is None:
                rows.append(tuple())
            else:
                rows.append(tuple(int(x) for x in row))
    except Exception as e:
        raise TypeError(f"Invalid canonical key structure: {key_like!r}") from e
    return tuple(rows)

def _infer_n_from_key(key: Tuple[Tuple[int, ...], ...]) -> int:
    """
    尝试从 canonical key 里推断参与者数量 n。
    """
    max_idx = -1
    for row in key:
        if row:
            mr = max(row)
            if mr > max_idx:
                max_idx = mr
    n_guess = max(len(key), max_idx + 1, 0)
    return n_guess

def _detect_inner_set_type(cls) -> Type:
    """
    尝试从 Distribution.initial(1).secrets 的内部元素类型推断使用 set 还是 frozenset；
    若无法判断，默认用 set。
    """
    try:
        probe = cls.initial(1)  # 你项目已有的方法
        secrets = getattr(probe, "secrets", None)
        if secrets and len(secrets) > 0:
            inner = next(iter(secrets))
            if isinstance(inner, frozenset):
                return frozenset
            if isinstance(inner, set):
                return set
    except Exception:
        pass
    return set  # 默认可变 set

def _coerce_groups_to_sets(key_can: Tuple[Tuple[int, ...], ...], inner_type: Type):
    """
    将 canonical key 转换为 Distribution 内部使用的集合容器。
    inner_type: set 或 frozenset
    返回同构容器（例如 tuple[set[int]] 或 tuple[frozenset[int]]）
    """
    if inner_type is frozenset:
        return tuple(frozenset(row) for row in key_can)
    else:
        return tuple(set(row) for row in key_can)

# -------- Distribution: classmethods --------
def _dist_from_secrets(cls, secrets_like: Any):
    """
    规范化 -> 转集合 -> 构造 Distribution
    优先 ctor(secrets=...) / ctor(...); 否则 initial(n) 后替换属性。
    """
    key_can = _to_canonical_tuple(secrets_like)
    inner_type = _detect_inner_set_type(cls)
    secrets_sets = _coerce_groups_to_sets(key_can, inner_type)

    # 1) 直接用构造器（若你的 Distribution 支持）
    try:
        return cls(secrets=secrets_sets)   # type: ignore[call-arg]
    except Exception:
        try:
            return cls(secrets_sets)       # type: ignore[call-arg]
        except Exception:
            pass

    # 2) 退回到 initial(n) + 替换属性（尽量调用带语义的方法）
    n = _infer_n_from_key(key_can)
    try:
        dist = cls.initial(n)
    except Exception as e:
        raise RuntimeError("Distribution.initial(n) not available for keys-only mode") from e

    # 如果有 with_secrets/replace/copy_with_secrets/set_secrets 等 API，优先使用
    for meth_name in ("with_secrets", "replace", "copy_with_secrets", "set_secrets"):
        m = getattr(dist, meth_name, None)
        if callable(m):
            try:
                new_dist = m(secrets=secrets_sets)  # 关键字参数
                return new_dist
            except TypeError:
                try:
                    new_dist = m(secrets_sets)      # 位置参数备选
                    return new_dist
                except Exception:
                    pass

    # 最后兜底：直接赋值属性
    try:
        object.__setattr__(dist, "secrets", secrets_sets)
    except Exception:
        setattr(dist, "secrets", secrets_sets)

    # 如果有 rebuild/normalize/recompute 之类方法，调用一下以刷新派生字段
    for hook in ("rebuild", "normalize", "recompute", "refresh"):
        h = getattr(dist, hook, None)
        if callable(h):
            try:
                h()
            except Exception:
                pass
    return dist

def _dist_from_canonical(cls, key_like: Any):
    return _dist_from_secrets(cls, key_like)

def _dist_from_key(cls, key_like: Any):
    return _dist_from_secrets(cls, key_like)

# 安装到 Distribution（作为 classmethod；若已有则不覆盖）
try:
    Distribution.from_secrets   # type: ignore[attr-defined]
except AttributeError:
    Distribution.from_secrets = classmethod(_dist_from_secrets)  # type: ignore[attr-defined]
try:
    Distribution.from_canonical  # type: ignore[attr-defined]
except AttributeError:
    Distribution.from_canonical = classmethod(_dist_from_canonical)  # type: ignore[attr-defined]
try:
    Distribution.from_key  # type: ignore[attr-defined]
except AttributeError:
    Distribution.from_key = classmethod(_dist_from_key)  # type: ignore[attr-defined]

# -------- ProtocolState: classmethod --------
def _ps_from_distribution(cls, dist, protocol: str):
    """
    优先已有的 from_distribution；否则退回 initial(dist, protocol)；
    再不行尝试 ctor(dist=..., protocol=...) / ctor(dist, protocol)。
    """
    existing = getattr(cls, "from_distribution", None)
    if existing and existing is not _ps_from_distribution and callable(existing):
        try:
            return existing(dist, protocol)
        except Exception:
            pass

    init = getattr(cls, "initial", None)
    if callable(init):
        try:
            return init(dist, protocol)
        except Exception:
            pass

    try:
        return cls(dist=dist, protocol=protocol)  # type: ignore[call-arg]
    except Exception:
        try:
            return cls(dist, protocol)            # type: ignore[call-arg]
        except Exception as e:
            raise RuntimeError(
                "Cannot construct ProtocolState from distribution; "
                "please ensure ProtocolState.initial(dist, protocol) exists."
            ) from e

if not hasattr(ProtocolState, "from_distribution"):
    ProtocolState.from_distribution = classmethod(_ps_from_distribution)  # type: ignore[attr-defined]
# =========================================================================
