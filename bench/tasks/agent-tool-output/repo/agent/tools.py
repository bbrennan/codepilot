import json

CATALOG = [
    {"sku": "SH-1", "name": "red running shoes"},
    {"sku": "SH-2", "name": "red leather shoes"},
    {"sku": "SH-3", "name": "blue running shoes"},
]


def search_products(query):
    """Tool: search the catalog. Returns the matches serialised as JSON (as the LLM tool API needs)."""
    words = query.lower().split()
    return json.dumps([p for p in CATALOG if all(w in p["name"] for w in words)])
