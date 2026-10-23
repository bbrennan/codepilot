import json

from . import tools


def handle(user_message):
    """Answer a shopping request using the search tool."""
    query = user_message.lower().replace("find", "").strip()
    results = json.loads(tools.search_products(query))
    if not results:
        return "Sorry, nothing matched."
    names = ", ".join(r["name"] for r in results)
    return f"Found {len(results)} products: {names}."
