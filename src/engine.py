# src/engine.py
from __future__ import annotations

from collections import deque
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Set, Tuple, List, Iterable, Optional
import time

from .model import Distribution, ProtocolState
from .protocols import permitted_calls
from .canonical import canonical_key

# --------- 能力探测：是否可由 canonical key 重建状态（启用 keys-only 模式） ---------
_HAS_DIST_FROM_CANONICAL = hasattr(Distribution, "from_canonical")
_HAS_DIST_FROM_SECRETS  = hasattr(Distribution, "from_secrets") or hasattr(Distribution, "from_key")
_HAS_PS_FROM_DIST       = hasattr(ProtocolState, "from_distribution")
_HAS_PS_INITIAL         = hasattr(ProtocolState, "initial")

_KEYS_MODE_AVAILABLE = (_HAS_DIST_FROM_CANONICAL or _HAS_DIST_FROM_SECRETS) and (_HAS_PS_FROM_DIST or _HAS_PS_INITIAL)

def _build_state_from_key(key, protocol: str) -> ProtocolState:
    """
    尝试用 (Distribution.from_canonical | from_secrets) + (ProtocolState.from_distribution | initial)
    从 canonical key 重建 ProtocolState。
    """
    # 构建 Distribution
    if _HAS_DIST_FROM_CANONICAL:
        dist = Distribution.from_canonical(key)  # type: ignore[attr-defined]
    elif _HAS_DIST_FROM_SECRETS:
        # 兼容不同命名：from_secrets / from_key
        ctor = getattr(Distribution, "from_secrets", None) or getattr(Distribution, "from_key", None)
        dist = ctor(key)
    else:
        raise RuntimeError("keys-only mode unavailable: Distribution lacks from_canonical/from_secrets")

    # 构建 ProtocolState
    if _HAS_PS_FROM_DIST:
        return ProtocolState.from_distribution(dist, protocol)  # type: ignore[attr-defined]
    elif _HAS_PS_INITIAL:
        # 复用 initial(dist, protocol) 作为“从分布构建状态”
        return ProtocolState.initial(dist, protocol)
    else:
        raise RuntimeError("keys-only mode unavailable: ProtocolState lacks from_distribution/initial")


# ---------- 子进程任务：展开一批（支持两种模式：'states' 或 'keys'） ----------
def _expand_batch(arg):
    """
    参数:
      arg = (mode, payload, protocol)
        - mode: 'states' | 'keys'
        - payload: List[ProtocolState] 或 List[CanonicalKey]
        - protocol: str
    返回:
      (out_keys, out_states_or_none)
        - keys: 去重后的 canonical keys 列表
        - states_or_none: 若 mode='states'，返回与 keys 一一对应的 ProtocolState 列表；若 mode='keys'，返回 None
    去重策略:
      - 对每个父状态做本地去重 (local_seen)
      - 对整个批次做一次去重 (batch_seen)
    """
    mode, payload, protocol = arg
    batch_seen = set()

    out_keys: List = []
    # states 模式下才会填充
    out_states: Optional[List[ProtocolState]] = [] if mode == "states" else None

    if mode == "states":
        states: List[ProtocolState] = payload
        for st in states:
            local_seen = set()
            local_pairs = []
            for call in permitted_calls(st, protocol):
                ns = st.update(call, protocol)
                k = canonical_key(ns.distribution.secrets)
                if k in local_seen:
                    continue
                local_seen.add(k)
                if k in batch_seen:
                    continue
                batch_seen.add(k)
                local_pairs.append((k, ns))
            if local_pairs:
                ks, sts = zip(*local_pairs)
                out_keys.extend(ks)
                out_states.extend(sts)  # type: ignore[arg-type]

    elif mode == "keys":
        keys: List = payload
        for k0 in keys:
            st = _build_state_from_key(k0, protocol)
            local_seen = set()
            for call in permitted_calls(st, protocol):
                ns = st.update(call, protocol)
                k = canonical_key(ns.distribution.secrets)
                if k in local_seen:
                    continue
                local_seen.add(k)
                if k in batch_seen:
                    continue
                batch_seen.add(k)
                out_keys.append(k)
        # keys-only 模式下不回传 states
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return out_keys, out_states


def chunked(seq: list, size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


class ReachabilityEngine:
    """在给定协议下，按层枚举可达等价类（canonical key）。"""

    def __init__(self, protocol: str):
        assert protocol in {"ANY", "CO", "LNS", "TOK", "SPI", "ATK"}, \
            f"Unknown protocol: {protocol}"
        self.protocol = protocol
        self._use_keys_mode = bool(_KEYS_MODE_AVAILABLE)

    # ----------------------------- 串行 BFS -----------------------------
    def bfs(self, n: int, max_depth: int = 10):
        start_dist = Distribution.initial(n)
        root_state = ProtocolState.initial(start_dist, self.protocol)

        start_key = canonical_key(start_dist.secrets)
        seen: Set[Tuple[Tuple[int, ...], ...]] = {start_key}
        layers: Dict[int, Set[Tuple[Tuple[int, ...], ...]]] = {0: {start_key}}
        queue = deque([(root_state, 0)])
        transitions = 0

        if max_depth == 0:
            return {
                "reachable_count": len(seen),
                "layers": layers,
                "layer_sizes": {d: len(s) for d, s in layers.items()},
                "transitions": 0,
            }

        while queue:
            state, depth = queue.popleft()
            if depth == max_depth:
                continue
            local_seen = set()
            for call in permitted_calls(state, self.protocol):
                new_state = state.update(call, self.protocol)
                key = canonical_key(new_state.distribution.secrets)
                if key in local_seen:
                    continue
                local_seen.add(key)
                transitions += 1
                if key not in seen:
                    seen.add(key)
                    queue.append((new_state, depth + 1))
                    layers.setdefault(depth + 1, set()).add(key)

        return {
            "reachable_count": len(seen),
            "layers": layers,
            "layer_sizes": {d: len(s) for d, s in layers.items()},
            "transitions": transitions,
        }

    # ------------------------ 分层并行 BFS（支持 keys-only / states 双模式） ------------------------
    def bfs_parallel(
        self,
        n: int,
        max_depth: int = 10,
        workers: int = 4,
        batch_size: int = 2048,   # 稍大默认，降低调度/IPC；可被命令行覆盖
        verbose: bool = True,
        heartbeat_every: int = 10,  # 每处理多少批打印一次心跳
    ):
        """
        Level-parallel BFS with a persistent ProcessPoolExecutor.
        Windows: 从脚本调用（if __name__ == '__main__':）。
        """
        start_dist = Distribution.initial(n)
        start_key = canonical_key(start_dist.secrets)

        # 初始前沿
        frontier_states: Optional[List[ProtocolState]] = None
        frontier_keys: Optional[List] = None

        if self._use_keys_mode:
            frontier_keys = [start_key]
        else:
            root = ProtocolState.initial(start_dist, self.protocol)
            frontier_states = [root]

        seen: Set[Tuple[Tuple[int, ...], ...]] = {start_key}
        layers: Dict[int, Set[Tuple[Tuple[int, ...], ...]]] = {0: {start_key}}
        transitions = 0

        if verbose:
            mode_name = "keys-only" if self._use_keys_mode else "states"
            print(f"[engine] parallel mode = {mode_name}", flush=True)

        if max_depth == 0:
            return {
                "reachable_count": len(seen),
                "layers": layers,
                "layer_sizes": {d: len(s) for d, s in layers.items()},
                "transitions": 0,
            }

        workers = max(1, int(workers))

        with ProcessPoolExecutor(max_workers=workers) as ex:
            for depth in range(max_depth):
                # 选择当前前沿视图
                if self._use_keys_mode:
                    frontier_len = len(frontier_keys or [])
                else:
                    frontier_len = len(frontier_states or [])

                if frontier_len == 0:
                    break

                if verbose:
                    print(f"[depth {depth}] frontier={frontier_len}  seen={len(seen)}",
                          flush=True)

                t0 = time.perf_counter()

                # 构造批次（keys 或 states）
                if self._use_keys_mode:
                    batches = [frontier_keys[i:i + batch_size] for i in range(0, frontier_len, batch_size)]  # type: ignore[index]
                    args_list = [("keys", b, self.protocol) for b in batches]
                else:
                    batches = [frontier_states[i:i + batch_size] for i in range(0, frontier_len, batch_size)]  # type: ignore[index]
                    args_list = [("states", b, self.protocol) for b in batches]

                cs = max(1, len(args_list) // (workers * 4)) if args_list else 1
                total_batches = len(args_list)

                # 新一层前沿
                next_frontier_states: Optional[List[ProtocolState]] = [] if not self._use_keys_mode else None
                next_frontier_keys: Optional[List] = [] if self._use_keys_mode else None

                for i, (keys, states_or_none) in enumerate(
                    ex.map(_expand_batch, args_list, chunksize=cs), start=1
                ):
                    transitions += len(keys)
                    if self._use_keys_mode:
                        for k in keys:
                            if k not in seen:
                                seen.add(k)
                                next_frontier_keys.append(k)  # type: ignore[union-attr]
                                layers.setdefault(depth + 1, set()).add(k)
                    else:
                        # states 模式：keys 与 states 一一对应
                        sts = states_or_none or []
                        for k, st in zip(keys, sts):
                            if k not in seen:
                                seen.add(k)
                                next_frontier_states.append(st)  # type: ignore[union-attr]
                                layers.setdefault(depth + 1, set()).add(k)

                    if verbose and (i % heartbeat_every == 0 or i == total_batches):
                        print(f"    processed {i}/{total_batches} batches", flush=True)

                # 切换到下一层前沿
                frontier_keys = next_frontier_keys if self._use_keys_mode else None
                frontier_states = next_frontier_states if not self._use_keys_mode else None

                if verbose:
                    t1 = time.perf_counter()
                    new_len = len(frontier_keys or frontier_states or [])
                    print(f"  -> new={new_len}  seen={len(seen)}  elapsed={t1 - t0:.2f}s",
                          flush=True)

        return {
            "reachable_count": len(seen),
            "layers": layers,
            "layer_sizes": {d: len(s) for d, s in layers.items()},
            "transitions": transitions,
        }
