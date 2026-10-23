from shop.cart import Cart


def test_carts_are_independent():
    a = Cart()
    a.add("A", 2)
    b = Cart()
    assert b.count() == 0
    assert a.count() == 2


def test_initial_items_still_supported():
    c = Cart([("X", 1)])
    c.add("Y", 3)
    assert c.count() == 4
