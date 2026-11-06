"""The conversation keeps room on a laptop screen: suggestion chips are for an empty session only, and the review bar's
summary is one line. (At 1280×800, with a plan and two changes waiting, the conversation had 317px of the column.)"""

from uihelpers import open_app


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")
    page.locator(".msg.user", has_text=text).last.wait_for()
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden", timeout=20_000)


def test_suggestions_show_before_the_first_message_only(page, server, session):
    open_app(page)
    assert page.locator("#quick button").first.is_visible()  # an empty session: ideas to start with
    send(page, "hello")
    assert page.locator("#quick").is_hidden()
    page.reload()
    page.locator(".msg.user", has_text="hello").wait_for()
    assert page.locator("#quick").is_hidden()  # still a conversation after a reload
    page.click("#newChatBtn")
    page.locator("#quick button").first.wait_for()  # a new session gets them back


def test_the_conversation_keeps_room_with_changes_and_a_plan_waiting(page, server, session):
    page.set_viewport_size({"width": 1280, "height": 800})
    open_app(page)
    send(page, "plan progress")
    send(page, "fix two things")
    page.locator("#reviewBar .rb-changes").wait_for()
    sizes = page.evaluate("""() => ({ transcript: document.querySelector('#transcript').clientHeight,
      summary: document.querySelector('.rb-changes .rb-main').getBoundingClientRect().height })""")
    assert sizes["summary"] <= 28, f"the review bar's summary isn't one line (as tall as its buttons): {sizes}"
    assert sizes["transcript"] >= 390, f"the conversation is squeezed: {sizes}"
    stats = page.locator(".rb-changes .dstat")
    assert stats.evaluate("(el) => el.getBoundingClientRect().right <= el.parentElement.getBoundingClientRect().right")
    assert "+2" in stats.text_content() and "−2" in stats.text_content()  # both, never cut: only file names give way
