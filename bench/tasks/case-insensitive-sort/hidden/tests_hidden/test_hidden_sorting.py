from catalog.sorting import sort_products


def test_ignores_case():
    items = [{"name": "Zebra cake", "sku": "1"}, {"name": "apple juice", "sku": "2"},
             {"name": "Banana", "sku": "3"}]
    assert [p["name"] for p in sort_products(items)] == ["apple juice", "Banana", "Zebra cake"]


def test_ties_by_sku():
    items = [{"name": "Milk", "sku": "M-2"}, {"name": "milk", "sku": "M-1"}, {"name": "MILK", "sku": "M-3"}]
    assert [p["sku"] for p in sort_products(items)] == ["M-1", "M-2", "M-3"]


def test_input_not_mutated():
    items = [{"name": "b", "sku": "1"}, {"name": "a", "sku": "2"}]
    sort_products(items)
    assert items[0]["name"] == "b"
