from src.canonical import canonical_key

def test_canonical_accepts_int_and_char():
    k1 = canonical_key([{0,1},{2}])
    k2 = canonical_key([{'A','B'},{'C'}])
    assert k1 == k2 == ((0,1),(2,))
