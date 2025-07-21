# src/metrics.py
from statistics import mean
from typing import List, Dict

def avg_branching(transitions: int, visited: int) -> float:
    # 粗略分支因子估计：扩展的总转换 / 已访问状态
    if visited == 0:
        return 0.0
    return transitions / visited
