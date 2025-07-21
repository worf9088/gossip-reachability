from src.engine import ReachabilityEngine

def test_reachability_n2_any():
    eng = ReachabilityEngine("ANY")
    res = eng.bfs(2)
    # n=2 理论上 reachable = 2 初始 + final?（初始 + 双向交换之后一个状态）
    assert res["reachable_count"] >= 2
