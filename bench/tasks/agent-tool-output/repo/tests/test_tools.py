import json

from agent.tools import search_products


def test_tool_returns_json():
    assert len(json.loads(search_products("red shoes"))) == 2
