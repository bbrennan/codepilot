"""A stand-in for an AgentCore entrypoint: parse the request, call the tool, answer."""

import re

from .catalog import search_products


def handle(user_message: str) -> dict:
    match = re.search(r"under \$?(\d+)", user_message)
    max_price = float(match.group(1)) if match else None
    query = re.sub(r"under \$?\d+", "", user_message).replace("find", "").strip()
    results = search_products(query, max_price)
    if not results:
        return {"answer": "Sorry, nothing matched.", "results": []}
    return {"answer": f"Found {len(results)} item(s).", "results": results}
