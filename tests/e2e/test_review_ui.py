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
    send(page, "run python once")
    page.locator("#reviewBar .rb-allow", has_text="always allow python").wait_for()
    page.check("#rbAllow")
    page.click("#rbApprove")
    wait_idle(page)
    assert "always allowed" in page.locator("#transcript .wait-row").text_content()
    send(page, "run python again")
    page.locator("#transcript .tool pre", has_text="ran-42").nth(1).wait_for(state="attached")  # no prompt
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


def test_pending_approval_survives_a_reload(page, server, session):
    open_app(page)
    send(page, "run ls")
    page.locator("#reviewBar .rb-approval").wait_for()
    page.reload()
    page.locator("#reviewBar .rb-approval", has_text="ls").wait_for()
