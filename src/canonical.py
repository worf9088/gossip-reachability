# src/canonical.py
from __future__ import annotations
from typing import Iterable, Any, List, Set, Tuple, Dict

__all__ = ["canonical_key"]

# ---------- helpers ----------
def _to_int(x: Any) -> int:
    """允许 int 或单字符 str（'A'..），其余类型报错。"""
    if isinstance(x, int):
        return x
    if isinstance(x, str) and len(x) == 1:
        return ord(x) - 65
    raise TypeError(f"canonical_key expects int or 1-char str, got {type(x).__name__}")

def _normalize_groups(secret_sets: Iterable[Iterable[Any]]) -> List[Set[int]]:
    """把输入规范为 List[Set[int]]，内部统一为 int。"""
    groups: List[Set[int]] = []
    for S in secret_sets:
        groups.append({_to_int(v) for v in S})
    return groups

def _relabel_compact(groups: List[Set[int]]) -> List[Tuple[int, ...]]:
    """
    按给定顺序紧致重标号（首次出现即分配 0..k-1），
    返回每个组的有序元组表示。
    """
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

# ---------- public ----------
def canonical_key(secret_sets: Iterable[Iterable[Any]]) -> Tuple[Tuple[int, ...], ...]:
    """
    稳定、通用的规范键：
      1) 允许 int / 单字符 str；
      2) 预扫描按 (-组大小, 组内容字典序) 排序；
      3) 用预扫描顺序进行紧致重标号；
      4) 最终按 (-组大小, 组内容字典序) 输出 (tuple of tuples)。
    示例：[{0,1},{2}] 与 [{'A','B'},{'C'}] -> ((0,1),(2,))
    """
    groups = _normalize_groups(secret_sets)
    # 预扫描顺序（决定紧致映射的先后）
    groups.sort(key=lambda g: (-len(g), tuple(sorted(g))))
    # 紧致重标号
    canon = _relabel_compact(groups)
    # 最终输出顺序
    canon.sort(key=lambda t: (-len(t), t))
    return tuple(canon)
