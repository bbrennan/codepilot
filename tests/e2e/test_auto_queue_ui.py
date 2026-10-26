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
    assert "Steering" in queued.text_content()  # Enter steers the running work
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


def test_sending_while_a_new_session_opens_uses_that_session(page, server, session):
    open_app(page)
    page.route("**/api/sessions", lambda route: (page.wait_for_timeout(400), route.continue_())[1]
               if route.request.method == "POST" else route.continue_())
    page.click("#newChatBtn")  # creating takes a moment...
    send(page, "hello from the new session")  # ...and the message is sent before it's open
    page.locator(".msg.user", has_text="hello from the new session").wait_for()
    wait_idle(page)
    assert len(server.store.list_sessions()) == 2  # the fixture's session plus exactly one new one
    newest = server.store.list_sessions()[0]
    assert server.store.live_messages(newest.id)[0]["content"][0]["text"] == "hello from the new session"


def test_queued_mid_turn_messages_have_no_broken_edit_buttons(page, server, session):
    open_app(page)
    send(page, "run python please")  # stops for approval
    page.locator("#reviewBar .rb-approval").wait_for()
    page.click("#rbApprove")
    wait_idle(page)
    assert page.locator(".msg.user .sent-while").count() == 0
    # every bubble that offers Edit must be one the server can rewind to
    mids = page.eval_on_selector_all(".msg.user[data-mid]", "els => els.map(e => +e.dataset.mid)")
    starts = [mid for mid, m in server.store.messages(session.id) if m["role"] == "user" and "text" in m["content"][0]]
    assert set(mids) <= set(starts)


def test_typing_while_an_approval_waits_declines_it_and_sends(page, server, session):
    open_app(page)
    send(page, "run ls")
    page.locator("#reviewBar .rb-approval").wait_for()
    wait_idle(page)
    send(page, "never mind, explain the code instead")
    page.locator(".wait-row.denied", has_text="you wrote a message instead").wait_for()
    assert page.locator("#reviewBar").is_hidden()
    wait_idle(page)
    assert "never mind, explain the code instead" in str(model_calls(server)[-1]["messages"][-1])
    assert server.store.get_session(session.id).pending is None


def test_old_servers_without_versions_get_a_warning(page, server, session):
    page.route("**/api/config", lambda route: route.fulfill(
        json={k: v for k, v in route.fetch().json().items() if k not in ("version", "stale")}))
    open_app(page, wait_tree=False)
    page.locator("#staleBanner", has_text="older than this page").wait_for()


def test_queue_runs_a_message_after_the_current_work(page, server, session):
    open_app(page)
    start_slow_reply(page)
    assert page.locator("#steerBtn").is_visible() and page.locator("#queueBtn").is_visible()
    page.fill("#input", "then summarise the repo")
    page.click("#queueBtn")
    queued = page.locator(".msg.queued")
    queued.wait_for()
    assert "runs when the current work finishes" in queued.text_content()
    page.fill("#input", "and keep it short")
    page.press("#input", "Tab")  # Tab queues too
    page.wait_for_function("() => document.querySelectorAll('.msg.queued').length === 2")
    wait_idle(page)
    calls = model_calls(server)
    # Each queued message ran as its own turn, in order, and can be edited like any message that starts a turn.
    assert len(calls) == 3
    assert calls[1]["messages"][-1]["content"][0]["text"].startswith("then summarise the repo")
    assert calls[2]["messages"][-1]["content"][0]["text"].startswith("and keep it short")
    page.locator(".msg.user[data-mid]", has_text="and keep it short").wait_for()


def test_a_waiting_message_can_switch_between_steer_and_queue(page, server, session):
    open_app(page)
    start_slow_reply(page)
    send(page, "steer me")
    bar = page.locator(".msg.queued .queued-bar")
    bar.locator("[data-qswitch]").click()
    page.locator(".msg.queued[data-when=after]").wait_for()
    assert "runs when the current work finishes" in bar.text_content()
    wait_idle(page)
    page.locator(".msg.user:not(.queued)", has_text="steer me").wait_for()


def test_a_reloaded_page_follows_the_running_turn_and_can_still_steer(page, server, session):
    open_app(page)
    send(page, "be very slow")
    page.locator(".msg.assistant", has_text="Thinking").wait_for()
    page.reload()
    page.locator("#stopBtn").wait_for()  # it knows codepilot is still working
    send(page, "one more thing")
    page.locator(".msg.queued").wait_for()  # steered, not refused as "already working"
    wait_idle(page)
    page.locator(".msg.user:not(.queued)", has_text="one more thing").wait_for()
    page.locator(".msg.assistant", has_text="Thinking slowly").first.wait_for()
    assert "one more thing" in str(model_calls(server)[-1]["messages"])
