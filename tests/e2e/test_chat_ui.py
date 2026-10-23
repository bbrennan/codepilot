"""Chat composer and transcript details: prompt history, long messages."""

import json

from uihelpers import open_app


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def test_up_and_down_recall_earlier_prompts(page, server, session):
    open_app(page)
    send(page, "first prompt")
    send(page, "second prompt")
    page.click("#input")
    page.keyboard.press("ArrowUp")
    assert page.input_value("#input") == "second prompt"
    page.keyboard.press("ArrowUp")
    assert page.input_value("#input") == "first prompt"
    page.keyboard.press("ArrowUp")  # oldest: stays put
    assert page.input_value("#input") == "first prompt"
    page.keyboard.press("ArrowDown")
    assert page.input_value("#input") == "second prompt"
    page.keyboard.press("ArrowDown")
    assert page.input_value("#input") == ""


def test_history_keeps_what_you_were_typing(page, server, session):
    open_app(page)
    send(page, "earlier question")
    page.type("#input", "half-written thought")
    page.keyboard.press("ArrowUp")
    assert page.input_value("#input") == "earlier question"
    page.keyboard.press("ArrowDown")
    assert page.input_value("#input") == "half-written thought"


def test_up_moves_the_caret_inside_multiline_text_first(page, server, session):
    open_app(page)
    send(page, "earlier question")
    page.click("#input")
    page.keyboard.type("line one")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("line two")
    page.keyboard.press("ArrowUp")  # caret is on the second line: move up, don't recall
    assert page.input_value("#input") == "line one\nline two"
    page.keyboard.press("ArrowUp")  # now on the first line: recall
    assert page.input_value("#input") == "earlier question"


def test_history_survives_a_reload(page, server, session):
    open_app(page)
    send(page, "remember me")
    page.reload()
    page.locator(".msg.user", has_text="remember me").wait_for()
    page.click("#input")
    page.keyboard.press("ArrowUp")
    assert page.input_value("#input") == "remember me"


def test_long_messages_collapse_and_expand(page, server, session):
    trace = json.dumps({"spans": [{"name": f"span-{i}", "status": "OK", "ms": i} for i in range(200)]}, indent=2)
    open_app(page)
    page.fill("#input", trace)
    page.press("#input", "Enter")
    msg = page.locator(".msg.user.long")
    msg.wait_for()
    assert "clamped" in msg.get_attribute("class")
    assert msg.locator(".body").bounding_box()["height"] < 260  # a few lines, not the whole trace
    more = msg.locator(".more").first
    assert "Show all (" in more.text_content() and "lines" in more.text_content()
    more.click()
    assert msg.locator(".body").bounding_box()["height"] > 2000
    assert more.text_content().strip() == "Show less"
    more.click()
    assert "clamped" in msg.get_attribute("class")

    msg.locator(".copy-msg").click()
    assert page.evaluate("() => navigator.clipboard.readText()").strip() == trace.strip()
    page.reload()  # replayed messages are collapsed too
    page.locator(".msg.user.long.clamped").wait_for()


def test_short_messages_are_not_collapsed(page, server, session):
    open_app(page)
    send(page, "a short question")
    assert page.locator(".msg.user .more").count() == 0
