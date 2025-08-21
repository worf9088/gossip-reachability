# scripts/debug_spi_n4.py
from __future__ import annotations
import sys, pathlib, collections

# 确保能 import src
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.engine import ReachabilityEngine
from src.model import Distribution, ProtocolState

# 与 tests 里的“无重标号”一致：组内升序 + 组间(大小降序, 组字典序)
def raw_key(secret_sets):
    canon = [tuple(sorted(g)) for g in secret_sets]
    canon.sort(key=lambda t: (-len(t), t))
    return tuple(canon)

def main():
    n = 4
    proto = "SPI"
    eng = ReachabilityEngine(proto)

    # 直接用 engine 的 BFS，但我们额外存 raw_key 映射
    start = Distribution.initial(n)
    root = ProtocolState.initial(start, proto)

    from collections import deque
    from src.canonical import canonical_key as std_canon

    seen_std = set([std_canon(start.secrets)])
    q = deque([root])

    bucket = collections.defaultdict(set)  # std_key -> set(raw_key)
    bucket[next(iter(seen_std))].add(raw_key(start.secrets))

    while q:
        st = q.popleft()
        for call in __import__("src.protocols", fromlist=[""]).permitted_calls(st, proto):
            ns = st.update(call, proto)
            k_std = std_canon(ns.distribution.secrets)
            k_raw = raw_key(ns.distribution.secrets)
            bucket[k_std].add(k_raw)
            if k_std not in seen_std:
                seen_std.add(k_std)
                q.append(ns)

    print(f"[debug] std_key count = {len(seen_std)}")
    # 找到最大“合并桶”
    merged = [(k, len(v)) for k, v in bucket.items()]
    merged.sort(key=lambda x: x[1], reverse=True)
    print(f"[debug] top merged sizes: {merged[:10]} (格式: (std_key, 合并raw_key数量))")

    # 打印第一个真正合并(>1)的桶，看看里面有哪些 raw_key
    first_multi = next(((k, v) for k, v in bucket.items() if len(v) > 1), None)
    if first_multi:
        k, raws = first_multi
        print("\n[debug] A merged bucket example:")
        print("std_key =", k)
        print("raw_keys in this bucket (each is a distinct state under no-relabel):")
        for rk in sorted(raws):
            print("  ", rk)
    else:
        print("[debug] No merged bucket found (then 15!=16 不是由 std_key 合并导致的)")

if __name__ == "__main__":
    main()
