from src.model import Distribution, ProtocolState
from src.protocols import permitted_calls

def make_state(protocol: str, n=3):
    d = Distribution.initial(n)
    return ProtocolState.initial(d, protocol)

def test_any_has_calls():
    st = make_state("ANY")
    calls = permitted_calls(st, "ANY")
    assert len(calls) == 3*2  # n*(n-1) = 6

def test_co_initial_all_pairs():
    st = make_state("CO")
    assert len(permitted_calls(st, "CO")) == 6

def test_lns_initial():
    st = make_state("LNS")
    # 初始时所有 caller 都能学到新 secret，仍是全对有向
    assert len(permitted_calls(st, "LNS")) == 6
