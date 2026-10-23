PRODUCTS = [
    {"sku": "SH-1", "name": "red running shoes", "price": 59.0},
    {"sku": "SH-2", "name": "red leather shoes", "price": 140.0},
    {"sku": "SH-3", "name": "blue running shoes", "price": 100.0},
]


def search_products(query, max_price=None):
    words = query.lower().split()
    hits = [p for p in PRODUCTS if all(w in p["name"] for w in words)]
    if max_price is not None:
        hits = [p for p in hits if p["price"] > max_price]
    return hits
