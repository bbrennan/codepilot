class Cart:
    def __init__(self, items=None):
        self.items = list(items) if items else []

    def add(self, sku, qty=1):
        if qty < 1:
            raise ValueError("qty must be >= 1")
        self.items.append((sku, qty))

    def count(self):
        return sum(q for _, q in self.items)
