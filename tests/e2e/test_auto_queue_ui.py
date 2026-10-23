"""Auto model routing, messages queued while codepilot works, and editing or retrying messages."""

from uihelpers import open_app


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def start_slow_reply(page):
    """Send a slow request and wait until the reply is streaming, so the model call is in flight."""
    send(page, "be slow")
    page.locator(".msg.assistant", has_text="Thinking").wait_for()


def model_calls(server):
    return [c for c in server.llm.calls if "messages" in c]


def test_new_sessions_default_to_auto_and_show_its_pick(page, server):
    open_app(page, wait_tree=False)
    page.click("#newChatBtn")
    page.wait_for_function("() => document.querySelector('#tier').value === 'tier:auto'")
    send(page, "rename a variable")
    chip = page.locator(".route-chip")
    chip.wait_for()
    assert "claude-sonnet-5-5" in chip.text_content() and "routine work" in chip.text_content()
    wait_idle(page)
    assert model_calls(server)[-1]["model"] == "anthropic.claude-sonnet-5-5"  # the newest Sonnet available
    send(page, "think hard about the design")
    page.locator(".route-chip", has_text="claude-opus-5-5").wait_for()


def test_a_message_typed_while_working_is_queued_then_sent(page, server, session):
    open_app(page)
    start_slow_reply(page)
    assert "queue" in page.get_attribute("#input", "placeholder").lower()
    send(page, "and also check the tests")
    queued = page.locator(".msg.queued")
    queued.wait_for()
    assert "Queued" in queued.text_content()
    wait_idle(page)
    page.locator(".msg.queued").wait_for(state="detached")  # became a normal message
    page.locator(".msg.user:not(.queued)", has_text="and also check the tests").wait_for()
    calls = model_calls(server)
    assert len(calls) == 2 and "and also check the tests" in str(calls[1]["messages"][-1])


def test_queued_message_can_be_removed_or_edited(page, server, session):
    open_app(page)
    start_slow_reply(page)
    send(page, "never mind this")
    page.locator(".msg.queued [data-qcancel]").click()
    page.locator(".msg.queued").wait_for(state="detached")
    send(page, "fix typo here")
    page.locator(".msg.queued [data-qedit]").click()
    page.wait_for_function("() => document.querySelector('#input').value === 'fix typo here'")  # back to change
    wait_idle(page)
    assert len(model_calls(server)) == 1


def test_stop_puts_queued_messages_back_in_the_box(page, server, session):
    open_app(page)
    start_slow_reply(page)
    send(page, "my follow-up")
    page.locator(".msg.queued").wait_for()
    page.click("#stopBtn")
    wait_idle(page)
    assert page.input_value("#input") == "my follow-up" and page.locator(".msg.queued").count() == 0


def test_edit_an_earlier_message_rewinds_the_conversation(page, server, session):
    open_app(page)
    send(page, "first question")
    wait_idle(page)
    send(page, "second question")
    wait_idle(page)
    first = page.locator(".msg.user", has_text="first question")
    first.hover()
    first.locator("[data-act=edit]").click()
    box = first.locator(".edit-box textarea")
    box.fill("first question, reworded")
    box.press("Enter")
    page.locator("#dialogTitle", has_text="Rewind to this message?").wait_for()
    page.click("#dialogOk")
    page.locator(".msg.user", has_text="first question, reworded").wait_for()
    wait_idle(page)
    assert page.locator(".msg.user", has_text="second question").count() == 0
    texts = [m["content"][0].get("text") for m in server.store.live_messages(session.id) if m["role"] == "user"]
    assert texts == ["first question, reworded"]
    page.reload()  # the edited conversation is what's stored
    page.locator(".msg.user", has_text="first question, reworded").wait_for()
    assert page.locator(".msg.user", has_text="second question").count() == 0


def test_retry_the_last_message(page, server, session):
    open_app(page)
    send(page, "hello there")
    wait_idle(page)
    msg = page.locator(".msg.user", has_text="hello there")
    msg.hover()
    msg.locator("[data-act=retry]").click()
    page.wait_for_function("() => document.querySelectorAll('.msg.assistant').length === 1")
    wait_idle(page)
    assert len(model_calls(server)) == 2 and page.locator(".msg.user", has_text="hello there").count() == 1
    assert len([m for m in server.store.live_messages(session.id) if m["role"] == "user"]) == 1


def test_up_arrow_still_recalls_prompts_after_edits(page, server, session):
    open_app(page)
    send(page, "one")
    wait_idle(page)
    page.click("#input")
    page.keyboard.press("ArrowUp")
    assert page.input_value("#input") == "one"
