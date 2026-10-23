from pricing.prices import clear_cache, get_price


def test_cached():
    clear_cache()
    calls = []
    fetch = lambda s, c: calls.append((s, c)) or 10
    assert get_price("A", "USD", fetch) == 10
    assert get_price("A", "USD", fetch) == 10
    assert len(calls) == 1
