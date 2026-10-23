from catalog.search import search_products


def test_words():
    assert [p["sku"] for p in search_products("red shoes")] == ["SH-1", "SH-2"]
