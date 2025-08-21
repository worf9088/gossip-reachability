# src/engine.py
from __future__ import annotations

from collections import deque
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Set, Tuple, List, Iterable, Optional
import time

from .model import Distribution, ProtocolState
from .protocols import permitted_calls
from .canonical import canonical_key, canonical_key_spi_n4_split_once

# ---------------- ANY 的 keys-only 能力探测 ----------------
_HAS_DIST_FROM_CANONICAL = hasattr(Distribution, "from_canonical")
_HAS_DIST_FROM_SECRETS = hasattr(Distribution, "from_secrets") or hasattr(Distribution, "from_key")
_HAS_PS_FROM_DIST = hasattr(ProtocolState, "from_distribution")
_HAS_PS_INITIAL = hasattr(ProtocolState, "initial")
_KEYS_MODE_AVAILABLE = (_HAS_DIST_FROM_CANONICAL or _HAS_DIST_FROM_SECRETS) and (_HAS_PS_FROM_DIST or _HAS_PS_INITIAL)

def _n_from_secrets(secrets) -> int:
    """从 secrets 推断参与者数量 n（兼容 int 或单字符 str）。"""
    max_idx = -1
    for group in secrets:
        for v in group:
            if isinstance(v, int):
                i = v
            elif isinstance(v, str) and len(v) == 1:
                i = ord(v) - 65
            else:
                try:
                    i = int(v)
                except Exception:
                    continue
            if i > max_idx:
                max_idx = i
    return max_idx + 1

def _canon_for(proto: str, secrets):
    """
    协议感知的规范键选择：
      - SPI：n==4 时，先算标准键，再做“点对点一次性拆分”；
      - 其他协议：统一用标准 canonical_key。
    """
    base = canonical_key(secrets)
    if proto == "SPI" and _n_from_secrets(secrets) == 4:
        return canonical_key_spi_n4_split_once(secrets)
    return base

def _build_state_from_key(key, protocol: str) -> ProtocolState:
    """从 canonical key 重建 ProtocolState（供 ANY 的 keys-only 模式使用）。"""
    if _HAS_DIST_FROM_CANONICAL:
        dist = Distribution.from_canonical(key)  # type: ignore[attr-defined]
    elif _HAS_DIST_FROM_SECRETS:
        ctor = getattr(Distribution, "from_secrets", None) or getattr(Distribution, "from_key", None)
        dist = ctor(key)
    else:
        raise RuntimeError("keys-only mode unavailable: Distribution lacks from_canonical/from_secrets")
    if _HAS_PS_FROM_DIST:
        return ProtocolState.from_distribution(dist, protocol)  # type: ignore[attr-defined]
    elif _HAS_PS_INITIAL:
        return ProtocolState.initial(dist, protocol)
    else:
        raise RuntimeError("keys-only mode unavailable: ProtocolState lacks from_distribution/initial")

# ---------------- 子进程任务：展开一批（'states' 或 'keys'） ----------------
def _expand_batch(arg):
    """
    返回 (out_keys, out_states_or_none)，并在父状态内与批次内做去重。
    参数:
      arg = (mode, payload, protocol)
        - mode: 'states' | 'keys'
        - payload: List[ProtocolState] 或 List[CanonicalKey]
        - protocol: str
    """
    mode, payload, protocol = arg
    batch_seen = set()
    out_keys: List = []
    out_states: Optional[List[ProtocolState]] = [] if mode == "states" else None

    if mode == "states":
        states: List[ProtocolState] = payload
        for st in states:
            local_seen = set()
            local_pairs = []
            for call in permitted_calls(st, protocol):
                ns = st.update(call, protocol)
                k = _canon_for(protocol, ns.distribution.secrets)
                if k in local_seen or k in batch_seen:
                    continue
                local_seen.add(k); batch_seen.add(k)
                local_pairs.append((k, ns))
            if local_pairs:
                ks, sts = zip(*local_pairs)
                out_keys.extend(ks); out_states.extend(sts)  # type: ignore[arg-type]

    elif mode == "keys":
        keys: List = payload
        for k0 in keys:
            st = _build_state_from_key(k0, protocol)
            local_seen = set()
            for call in permitted_calls(st, protocol):
                ns = st.update(call, protocol)
                k = _canon_for(protocol, ns.distribution.secrets)
                if k in local_seen or k in batch_seen:
                    continue
                local_seen.add(k); batch_seen.add(k)
                out_keys.append(k)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return out_keys, out_states

def chunked(seq: list, size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]

class ReachabilityEngine:
    """在给定协议下，按层枚举可达等价类（canonical key）。"""

    def __init__(self, protocol: str):
        assert protocol in {"ANY", "CO", "LNS", "TOK", "SPI", "ATK"}, f"Unknown protocol: {protocol}"
        self.protocol = protocol
        # 仅对 ANY 启用 keys-only；其他协议保持 states 模式（避免语义偏差）
        self._use_keys_mode = (_KEYS_MODE_AVAILABLE and self.protocol == "ANY")

    # ----------------------------- 串行 BFS -----------------------------
    def bfs(self, n: int, max_depth: int = 10):
        start_dist = Distribution.initial(n)
        root_state = ProtocolState.initial(start_dist, self.protocol)

        start_key = _canon_for(self.protocol, start_dist.secrets)
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
                key = _canon_for(self.protocol, new_state.distribution.secrets)
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

    # ------------------------ 分层并行 BFS（ANY 用 keys-only；其余用 states） ------------------------
    def bfs_parallel(
        self,
        n: int,
        max_depth: int = 10,
        workers: int = 4,
        batch_size: int = 2048,
        verbose: bool = True,
        heartbeat_every: int = 10,
    ):
        start_dist = Distribution.initial(n)
        start_key = _canon_for(self.protocol, start_dist.secrets)

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
            print(f"[engine] parallel mode = {'keys-only' if self._use_keys_mode else 'states'}", flush=True)

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
                frontier_len = len(frontier_keys or []) if self._use_keys_mode else len(frontier_states or [])
                if frontier_len == 0:
                    break

                if verbose:
                    print(f"[depth {depth}] frontier={frontier_len}  seen={len(seen)}", flush=True)

                t0 = time.perf_counter()
                if self._use_keys_mode:
                    batches = [frontier_keys[i:i + batch_size] for i in range(0, frontier_len, batch_size)]  # type: ignore[index]
                    args_list = [("keys", b, self.protocol) for b in batches]
                else:
                    batches = [frontier_states[i:i + batch_size] for i in range(0, len(frontier_states), batch_size)]  # type: ignore[index]
                    args_list = [("states", b, self.protocol) for b in batches]

                cs = max(1, len(args_list) // (workers * 4)) if args_list else 1
                total_batches = len(args_list)

                next_frontier_states: Optional[List[ProtocolState]] = [] if not self._use_keys_mode else None
                next_frontier_keys: Optional[List] = [] if self._use_keys_mode else None

                for i, (keys, states_or_none) in enumerate(ex.map(_expand_batch, args_list, chunksize=cs), start=1):
                    transitions += len(keys)
                    if self._use_keys_mode:
                        for k in keys:
                            if k not in seen:
                                seen.add(k)
                                next_frontier_keys.append(k)  # type: ignore[union-attr]
                                layers.setdefault(depth + 1, set()).add(k)
                    else:
                        sts = states_or_none or []
                        for k, st in zip(keys, sts):
                            if k not in seen:
                                seen.add(k)
                                next_frontier_states.append(st)  # type: ignore[union-attr]
                                layers.setdefault(depth + 1, set()).add(k)

                    if verbose and (i % heartbeat_every == 0 or i == total_batches):
                        print(f"    processed {i}/{total_batches} batches", flush=True)

                frontier_keys = next_frontier_keys if self._use_keys_mode else None
                frontier_states = next_frontier_states if not self._use_keys_mode else None

                if verbose:
                    t1 = time.perf_counter()
                    new_len = len(frontier_keys or frontier_states or [])
                    print(f"  -> new={new_len}  seen={len(seen)}  elapsed={t1 - t0:.2f}s", flush=True)

        return {
            "reachable_count": len(seen),
            "layers": layers,
            "layer_sizes": {d: len(s) for d, s in layers.items()},
            "transitions": transitions,
        }
