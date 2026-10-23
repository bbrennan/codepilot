class Cart:
    def __init__(self, items=[]):
        self.items = items

    def add(self, sku, qty=1):
        if qty < 1:
            raise ValueError("qty must be >= 1")
        self.items.append((sku, qty))

    def count(self):
        return sum(q for _, q in self.items)
