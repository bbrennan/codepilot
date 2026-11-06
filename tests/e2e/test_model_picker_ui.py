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
    assert "pending onboarding" in off.text_content()  # also visible text, so keyboard and screen-reader users get it
    assert page.locator("#tier option[value='model:anthropic.claude-sonnet-5-5']").is_enabled()


# -- a narrow chat header, and what a page load says ----------------------------------------------------------------


def test_the_header_shows_the_session_title_and_short_model_names_on_a_narrow_window(page, server, session):
    page.set_viewport_size({"width": 1024, "height": 640})
    open_app(page)
    page.wait_for_function("() => document.querySelector('#tier option[value=\"tier:main\"]')")
    title = page.locator("#chatTitle")
    assert title.evaluate("(el) => el.scrollWidth <= el.clientWidth"), f"title cut: {title.bounding_box()}"
    shown = page.evaluate("() => document.querySelector('#tier').selectedOptions[0].textContent")
    assert "anthropic." not in shown and "sonnet-5-5" in shown  # the model, not its provider's prefix
    # Every form of a Bedrock id comes out the same: no region, no provider prefix, no date or version suffix.
    for full in ["anthropic.claude-sonnet-5-5", "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                 "global.anthropic.claude-opus-5-5"]:
        assert page.evaluate("(m) => shortModel(m)", full) == full.split("anthropic.")[1].split("-2025")[0]


def test_a_page_load_doesnt_toast_what_the_model_picker_already_shows(page, server, session):
    open_app(page)
    # The picker says it once the model list arrives (the same moment the toast used to show): wait for that.
    page.locator("#tier option[value='tier:fast']", has_text="(fallback)").wait_for(state="attached")
    assert page.locator(".toast", has_text="not enabled").count() == 0  # it covered the bottom panel at every load
    fallback = {**MODELS, "tiers": {"fast": {"model": "anthropic.claude-haiku-4-5", "fallback": True,
                                             "configured": "anthropic.claude-haiku-5-5"}}}
    page.route("**/api/models?refresh=1", lambda route: route.fulfill(status=200, content_type="application/json",
                                                                      body=json.dumps(fallback)))
    page.select_option("#tier", "refresh")  # asking for a check still reports it
    page.locator(".toast", has_text="fast: claude-haiku-5-5 not enabled, using claude-haiku-4-5").wait_for()
