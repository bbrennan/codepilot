from . import tools


def handle(user_message):
    """Answer a shopping request using the search tool."""
    query = user_message.lower().replace("find", "").strip()
    results = tools.search_products(query)
    if not results:
        return "Sorry, nothing matched."
    names = ", ".join(r["name"] for r in results) if isinstance(results, list) else ""
    return f"Found {len(results)} products." + (f" {names}." if names else "")
