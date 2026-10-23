from shop.cart import Cart


def test_add():
    c = Cart()
    c.add("A", 2)
    assert c.count() >= 2
