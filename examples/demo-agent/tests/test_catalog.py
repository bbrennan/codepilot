from demo_agent.catalog import search_products


def test_search_by_words():
    assert [p["sku"] for p in search_products("red shoes")] == ["SH-1", "SH-2"]


def test_max_price_keeps_cheaper_items():
    assert [p["sku"] for p in search_products("red shoes", max_price=100)] == ["SH-1"]
