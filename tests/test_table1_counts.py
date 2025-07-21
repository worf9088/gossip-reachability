# tests/test_table1_counts.py
from src.enumerator import count_reachable

expected = {
    2: dict.fromkeys(["LNS", "CO", "SPI", "TOK", "ANY"], 2),
    3: dict.fromkeys(["LNS", "CO", "SPI", "TOK", "ANY"], 4),
    4: {"LNS": 15, "CO": 15, "SPI": 16, "TOK": 16, "ANY": 16},
}

def test_counts():
    for n, pc in expected.items():
        for proto, exp in pc.items():
            assert count_reachable(proto, n, depth=10) == exp
