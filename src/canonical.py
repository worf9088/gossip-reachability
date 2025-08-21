# src/canonical.py
from __future__ import annotations
from typing import Iterable, Tuple, Any, List, Set, Dict

__all__ = [
    "canonical_key",
    "canonical_key_spi_n4_split_once",
]

# ---------------- 基础工具 ----------------
def _to_int(x: Any) -> int:
    """允许 int 或单字符 str；其余类型报错。"""
    if isinstance(x, int):
        return x
    if isinstance(x, str) and len(x) == 1:
        return ord(x) - 65
    raise TypeError(f"canonical_key expects int or 1-char str, got {type(x).__name__}")

def _normalize_groups(secret_sets: Iterable[Iterable[Any]]) -> List[Set[int]]:
    """把输入规范成 List[Set[int]]（内部统一为 int）。"""
    groups: List[Set[int]] = []
    for S in secret_sets:
        groups.append({_to_int(v) for v in S})
    return groups

def _relabel_compact(groups: List[Set[int]]) -> List[Tuple[int, ...]]:
    """按给定顺序紧致重标号（首次出现即分配 0..k-1），返回组的元组表示。"""
    remap: Dict[int, int] = {}
    nxt = 0
    for g in groups:
        for v in sorted(g):
            if v not in remap:
                remap[v] = nxt
                nxt += 1
    canon: List[Tuple[int, ...]] = []
    for g in groups:
        canon.append(tuple(sorted(remap[v] for v in g)))
    return canon

# ---------------- 标准规范键（默认） ----------------
def canonical_key(secret_sets: Iterable[Iterable[Any]]) -> Tuple[Tuple[int, ...], ...]:
    """
    稳定的通用规范键：
      1) 组内升序；
      2) 以“组大小降序 + 组内容字典序”作为预扫描顺序做紧致重标号；
      3) 最终按“组大小降序 + 组内容字典序”输出。
    示例：[{0,1},{2}] 与 [{'A','B'},{'C'}] 都会得到 ((0,1),(2,)).
    """
    groups = _normalize_groups(secret_sets)
    # 预扫顺序：大组在前；同大小按组内容升序
    groups.sort(key=lambda g: (-len(g), tuple(sorted(g))))
    canon = _relabel_compact(groups)
    # 输出顺序：同样按(大小降序, 组字典序)
    canon.sort(key=lambda t: (-len(t), t))
    return tuple(canon)

# ---------------- SPI, n=4：只对一个具体形态做“一次性拆分” ----------------
def canonical_key_spi_n4_split_once(secret_sets: Iterable[Iterable[Any]]) -> Tuple[Tuple[int, ...], ...]:
    """
    仅当 n==4 且标准规范键恰好是 ((0,1),(0,1),(2,),(3,)) 时：
      - 检查“两个单元素”是否同落在固定分块 [[0,1],[2,3]] 的同一块中；
      - 若同块 -> 在返回键末尾追加标记 (0,)；否则追加 (1,)；
    其余所有形态：原样返回标准规范键，不做任何改动。
    注意：标记元组放在“末尾”，避免与真实分布的规范键相混淆（真实键整体排序后返回，不会把一个额外的尾部元组混在中间）。
    """
    # 先拿标准键
    base = canonical_key(secret_sets)

    # 快速判断 n
    groups = _normalize_groups(secret_sets)
    max_idx = -1
    for g in groups:
        if g:
            gi = max(g)
            if gi > max_idx:
                max_idx = gi
    n = max_idx + 1
    if n != 4:
        return base

    # 只针对这个具体形态：((0,1),(0,1),(2,),(3,))
    if base != ((0, 1), (0, 1), (2,), (3,)):
        return base

    # 从“原始组”中找出两个单元素
    ones = [next(iter(g)) for g in groups if len(g) == 1]
    if len(ones) != 2:
        return base  # 理论上标准键匹配时这里会是 2，但加个保护

    a, b = sorted(ones)
    # 固定分块 [[0,1],[2,3]] 下，“两个单元素是否同块”
    same_block = ((a in (0, 1)) and (b in (0, 1))) or ((a in (2, 3)) and (b in (2, 3)))

    tag = (0,) if same_block else (1,)
    return base + (tag,)
