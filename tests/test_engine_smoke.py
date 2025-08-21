from src.engine import ReachabilityEngine

def test_smoke_any_depth0():
    eng = ReachabilityEngine("ANY")
    res = eng.bfs(n=5, max_depth=0)
    assert res["reachable_count"] >= 1
    assert 0 in res["layers"]
    assert res["layer_sizes"][0] == len(res["layers"][0])

def test_parallel_matches_serial_small():
    eng = ReachabilityEngine("ANY")
    s = eng.bfs(n=5, max_depth=3)
    p = eng.bfs_parallel(n=5, max_depth=3, workers=2, batch_size=8, verbose=False)
    # 只比对层数与总可达数（避免状态内部顺序/对象差异）
    assert sum(len(v) for v in s["layers"].values()) == sum(len(v) for v in p["layers"].values())
    assert s["reachable_count"] == p["reachable_count"]
