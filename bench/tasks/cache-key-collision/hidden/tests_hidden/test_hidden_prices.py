from pricing.prices import clear_cache, get_price

RATES = {"USD": 100, "EUR": 92}


def test_currencies_separate():
    clear_cache()
    calls = []

    def fetch(sku, cur):
        calls.append((sku, cur))
        return RATES[cur]
    assert get_price("A", "EUR", fetch) == 92
    assert get_price("A", "USD", fetch) == 100
    assert get_price("A", "EUR", fetch) == 92
    assert get_price("A", fetch=fetch) == 100
    assert sorted(calls) == [("A", "EUR"), ("A", "USD")]
