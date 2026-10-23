_cache = {}


def clear_cache():
    _cache.clear()


def get_price(sku, currency="USD", fetch=None):
    """Price of sku in currency, cached. fetch(sku, currency) calls the price service."""
    key = (sku, currency)
    if key in _cache:
        return _cache[key]
    price = fetch(sku, currency)
    _cache[key] = price
    return price
