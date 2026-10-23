def sort_products(products):
    """Products sorted A-Z by name."""
    return sorted(products, key=lambda p: (p["name"].casefold(), p["sku"]))
