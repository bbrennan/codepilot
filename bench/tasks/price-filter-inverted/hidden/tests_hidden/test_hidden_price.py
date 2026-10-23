from catalog.search import search_products


def test_budget():
    assert [p["sku"] for p in search_products("red shoes", max_price=100)] == ["SH-1"]


def test_boundary_inclusive():
    assert [p["sku"] for p in search_products("running shoes", max_price=100)] == ["SH-1", "SH-3"]


def test_no_limit():
    assert len(search_products("shoes")) == 3
