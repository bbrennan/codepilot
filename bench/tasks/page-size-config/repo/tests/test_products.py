from api.products import list_products


def test_explicit_size():
    assert len(list_products(list(range(50)), page_size=5)) == 5
