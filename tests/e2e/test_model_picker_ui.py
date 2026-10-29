"""The model picker explains models the account can't use instead of silently hiding them."""

import json

from uihelpers import open_app

MODELS = {"provider": "bedrock", "checked_at": 1, "tiers": {}, "models": [
    {"id": "anthropic.claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "available": True, "reason": "ok",
     "api": "Messages API", "window": 1000000, "newest": True},
    {"id": "anthropic.claude-haiku-5-5", "label": "Claude Haiku 5.5", "available": False,
     "reason": "Model access is pending onboarding for this account", "api": "Messages API", "window": 1000000},
]}


def test_unavailable_models_are_listed_disabled_with_their_reason(page, server, session):
    page.route("**/api/models*", lambda route: route.fulfill(status=200, content_type="application/json",
                                                              body=json.dumps(MODELS)))
    open_app(page)
    page.wait_for_function("() => document.querySelector('#tier option[value=\"model:anthropic.claude-sonnet-5-5\"]')")
    off = page.locator("#tier option[value='off:anthropic.claude-haiku-5-5']")
    assert off.count() == 1 and off.is_disabled()
    assert "pending onboarding" in off.get_attribute("title")
    assert page.locator("#tier option[value='model:anthropic.claude-sonnet-5-5']").is_enabled()
