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


def test_the_summary_keeps_its_count_and_stats_at_the_narrowest_chat(page, server, session):
    """The chat can be dragged down to 300px. There the buttons wrap under the summary rather than clip it."""
    from codepilot import tools
    root = server.repo.resolve()
    ctx = tools.ToolContext(root=root, cfg=server.cfg, store=server.store, session_id=session.id)
    tools.propose_edit(ctx, "big_module.py", "", "".join(f"value_{i} = {i}\n" for i in range(1234)))
    tools.propose_edit(ctx, "agent/core.py", "a - b", "a + b")
    page.set_viewport_size({"width": 1280, "height": 800})
    page.add_init_script("localStorage.setItem('cp--chat-w', '300px')")
    open_app(page)
    page.locator("#reviewBar .rb-changes").wait_for()
    assert round(page.locator(".chat").bounding_box()["width"]) == 300
    whole = page.evaluate("""() => { const main = document.querySelector('.rb-changes .rb-main').getBoundingClientRect();
      return [...document.querySelectorAll('.rb-changes .rb-main > b, .rb-changes .rb-main > .dstat')]
        .map((el) => ({ text: el.textContent, inside: el.getBoundingClientRect().right <= main.right + 0.5 })); }""")
    assert all(w["inside"] for w in whole), f"clipped: {whole}"
    assert "+1235" in whole[1]["text"] and "−1" in whole[1]["text"]
    assert page.locator("#rbApplyAll").is_visible()  # the buttons are all still there, on their own line if need be
