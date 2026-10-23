from catalog.sorting import sort_products


def test_basic():
    out = sort_products([{"name": "b", "sku": "1"}, {"name": "a", "sku": "2"}])
    assert [p["name"] for p in out] == ["a", "b"]
