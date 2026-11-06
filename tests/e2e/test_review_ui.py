"""Reviewing changes and approving commands: the bar above the composer and the Review tab."""

from uihelpers import open_app


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def mod(page):
    return "Meta" if page.evaluate("navigator.platform").startswith("Mac") else "Control"


def test_command_approval_lives_in_the_bar_not_the_chat(page, server, session):
    open_app(page)
    send(page, "run python please")
    bar = page.locator("#reviewBar .rb-approval")
    bar.wait_for()
    assert "python -c" in bar.text_content()
    assert page.locator("#transcript .wait-row.waiting").count() == 1  # a one-line marker in the chat
    page.keyboard.press(f"{mod(page)}+Enter")  # approve from anywhere
    page.locator("#transcript .tool pre", has_text="ran-42").wait_for(state="attached")
    wait_idle(page)
    assert page.locator("#reviewBar").is_hidden()
    assert "Approved" in page.locator("#transcript .wait-row").text_content()


def test_deny(page, server, session):
    open_app(page)
    send(page, "run ls")
    page.locator("#rbDeny").click()
    page.locator("#transcript .wait-row.denied").wait_for()
    wait_idle(page)
    assert page.locator("#reviewBar").is_hidden()


def test_always_allow_for_the_session(page, server, session):
    open_app(page)
    send(page, "run a module once")
    page.locator("#reviewBar .rb-allow", has_text="always allow python -m platform").wait_for()
    page.check("#rbAllow")
    page.click("#rbApprove")
    wait_idle(page)
    assert "always allowed" in page.locator("#transcript .wait-row").text_content()
    send(page, "run a module again")
    page.locator("#transcript .tool .st.ok").nth(1).wait_for()  # ran, with no prompt
    wait_idle(page)
    assert page.locator("#reviewBar").is_hidden()
    send(page, "run ls")  # a different command still asks
    page.locator("#reviewBar .rb-approval").wait_for()


def test_changes_collect_in_the_bar_and_review_tab(page, server, session):
    open_app(page)
    send(page, "fix two things")
    bar = page.locator("#reviewBar .rb-changes")
    bar.wait_for()
    wait_idle(page)
    assert "2 changes to review" in bar.text_content() and "+2" in bar.text_content()
    assert page.locator("details.card.prop[open]").count() == 0  # compact in the chat
    page.click("#rbReview")
    page.locator(".review .rv-item.on", has_text="core.py").wait_for()
    assert "a + b" in page.locator(".review .ed-scroll").text_content()
    page.keyboard.press("a")  # apply, then jump to the next waiting change
    page.locator(".review .rv-item.on", has_text="test_core.py").wait_for()
    assert "a + b" in (server.repo / "agent/core.py").read_text()
    assert "1 change to review" in page.locator("#reviewBar").text_content()
    page.keyboard.press("r")
    page.wait_for_function("() => document.querySelector('#reviewBar').hidden")
    assert "# 1 + 2" not in (server.repo / "tests/test_core.py").read_text()


def test_apply_all_from_the_bar(page, server, session):
    open_app(page)
    send(page, "fix two things")
    page.locator("#rbApplyAll").click()
    page.wait_for_function("() => document.querySelector('#reviewBar').hidden")
    assert "a + b" in (server.repo / "agent/core.py").read_text()
    assert "# 1 + 2" in (server.repo / "tests/test_core.py").read_text()
    assert page.locator("#transcript .card.prop .status.applied").count() == 2


def test_ask_for_a_change_from_the_review_tab(page, server, session):
    open_app(page)
    send(page, "fix the add bug")
    page.locator("#rbReview").click()
    wait_idle(page)
    page.fill("#rvAsk", "also add a docstring")
    page.press("#rvAsk", "Enter")
    page.locator(".msg.user", has_text="About change #1 to agent/core.py: also add a docstring").wait_for()


def test_inline_code_is_never_offered_always_allow(page, server, session):
    open_app(page)
    send(page, "run python please")  # python -c "...": a rule for it would cover any code
    page.locator("#reviewBar .rb-approval").wait_for()
    assert page.locator("#rbAllow").count() == 0


def test_pending_approval_survives_a_reload(page, server, session):
    open_app(page)
    send(page, "run ls")
    page.locator("#reviewBar .rb-approval").wait_for()
    page.reload()
    page.locator("#reviewBar .rb-approval", has_text="ls").wait_for()


def test_applied_changes_stay_closed_after_a_restart(page, server, session):
    from conftest import LiveServer, ScriptedLLM

    from codepilot.agent import Agent
    from codepilot.server import create_app
    from codepilot.store import Store

    open_app(page)
    send(page, "fix two things")
    page.locator("#rbApplyAll").click()
    page.wait_for_function("() => document.querySelector('#reviewBar').hidden")
    wait_idle(page)
    page.goto("about:blank")  # leave first: a page still open would poll the dead server and log connection errors
    server.stop()  # shut codepilot down, then relaunch it on the same data
    store = Store(server.cfg.home)
    relaunched = LiveServer(create_app(server.cfg, store, Agent(server.cfg, store, llm=ScriptedLLM())))
    try:
        page.goto(relaunched.url + "/")
        page.locator("#transcript .card.prop").first.wait_for()
        assert page.locator("#reviewBar").is_hidden()
        assert page.locator("#transcript .card.prop .status").all_text_contents() == ["applied", "applied"]
        assert page.locator("#transcript details.card.prop[open]").count() == 0
        # each change is shown where it was proposed, right after its tool call, not piled up at the end
        assert page.evaluate("""() => [...document.querySelectorAll('#transcript > *')]
            .findIndex(el => el.matches('.card.prop')) < document.querySelectorAll('#transcript > *').length - 3""")
    finally:
        try:
            page.goto("about:blank")  # same reason as above: don't leave the page polling a server about to stop
        finally:
            relaunched.stop()


def test_a_change_made_stale_elsewhere_stops_waiting(page, server, session):
    open_app(page)
    send(page, "fix the add bug")
    page.locator("#reviewBar .rb-changes").wait_for()
    wait_idle(page)
    (server.repo / "agent/core.py").write_text("def add(a, b):\n    return b + a\n")  # fixed by hand
    page.reload()
    page.locator("#transcript .card.prop .status.outdated").wait_for()
    assert page.locator("#reviewBar").is_hidden()


def test_a_double_click_on_apply_sends_one_request(page, server, session):
    open_app(page)
    send(page, "fix the add bug")
    wait_idle(page)
    held = []
    page.route("**/api/proposals/*/apply", lambda route: held.append(route))  # the first click is still on its way
    button = page.locator("#transcript [data-apply]").first
    button.click()
    button.click(force=True)
    page.wait_for_timeout(300)
    assert len(held) == 1
    held[0].continue_()
    page.locator("#transcript .card.prop .status.applied").wait_for()
    assert (server.repo / "agent/core.py").read_text().count("a + b") == 1


def test_writing_instead_of_approving_keeps_an_attached_screenshot(page, server, session, tmp_path):
    import base64
    open_app(page)
    send(page, "a long command please")  # a command waits for approval
    page.locator("#reviewBar .rb-approval").wait_for()
    (tmp_path / "shot.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="))
    page.set_input_files("#imgFile", str(tmp_path / "shot.png"))
    page.locator("#attachTray img").wait_for()
    send(page, "don't run that; look at this screenshot")
    wait_idle(page)
    page.locator("#transcript img[src^='/api/images/']").first.wait_for()  # shown in the chat
    sent = server.llm.calls[-1]["messages"][-1]["content"]
    assert any("image" in b for b in sent) and any("toolResult" in b for b in sent)  # with the decline
    # And the turn went on: codepilot answered, nothing failed on the way.
    assert page.locator("#transcript .banner.error").count() == 0
    assert page.locator(".msg.assistant").last.inner_text().strip() == "Done."


ONE_LINE = "(sel) => { const r = document.querySelector(sel); return r.getBoundingClientRect().height <= 24 }"


def test_a_long_command_waiting_for_approval_is_one_line_in_the_chat(page, server, session):
    """The command is shown in full once, in the review bar; the chat keeps a one-line marker of it."""
    open_app(page)
    send(page, "a long command please")  # a 30-line script
    page.locator("#reviewBar .rb-approval").wait_for()
    row = page.locator("#transcript .wait-row.waiting")
    assert page.evaluate(ONE_LINE, "#transcript .wait-row.waiting"), row.bounding_box()
    assert "step 29" in row.get_attribute("title")  # the whole command, on hover
    assert "see the bar below" not in row.inner_text()
    page.click("#rbApprove")
    page.locator("#transcript .wait-row.approved").wait_for()
    assert page.evaluate(ONE_LINE, "#transcript .wait-row.approved"), "the decision is one line too"
