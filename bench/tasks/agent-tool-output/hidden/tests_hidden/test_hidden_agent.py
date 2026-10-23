import json

from agent.agent import handle
from agent.tools import search_products


def test_answer():
    assert handle("find red shoes") == "Found 2 products: red running shoes, red leather shoes."


def test_no_match():
    assert handle("find purple hats") == "Sorry, nothing matched."


def test_tool_contract_unchanged():
    assert isinstance(search_products("red"), str)
    assert len(json.loads(search_products("shoes"))) == 3
