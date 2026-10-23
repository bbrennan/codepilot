_cache = {}


def clear_cache():
    _cache.clear()


def get_price(sku, currency="USD", fetch=None):
    """Price of sku in currency, cached. fetch(sku, currency) calls the price service."""
    if sku in _cache:
        return _cache[sku]
    price = fetch(sku, currency)
    _cache[sku] = price
    return price
