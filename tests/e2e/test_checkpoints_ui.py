"""Turn checkpoints: undoing a turn's file changes, alone or along with Edit and Retry."""

from uihelpers import open_app


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def two_applied_changes(page, server):
    """Auto-apply on, then the scripted "fix two" turn writes agent/core.py and tests/test_core.py."""
    open_app(page)
    page.check("#autoApply")
    send(page, "fix two")
    wait_idle(page)
    assert "a + b" in (server.repo / "agent/core.py").read_text()
    assert "# 1 + 2" in (server.repo / "tests/test_core.py").read_text()


def statuses(server, session):
    return [p.status for p in server.store.list_proposals(session.id)]


def test_edit_can_undo_the_rewound_turns_file_changes(page, server, session):
    two_applied_changes(page, server)
    send(page, "hello again")
    wait_idle(page)
    first = page.locator(".msg.user", has_text="fix two")
    first.hover()
    first.locator("[data-act=edit]").click()
    first.locator(".edit-box textarea").fill("just say hi")
    first.locator(".edit-box textarea").press("Enter")
    page.locator("#dialogTitle", has_text="Rewind to this message?").wait_for()
    rows = page.locator("#dialogExtra .cp-row")
    assert rows.count() == 2 and "agent/core.py" in rows.first.text_content() + rows.last.text_content()
    assert page.is_checked("#cpRestore") and "Also undo these 2 file changes" in page.text_content("#dialogExtra")
    assert "commands, the terminal or other editors" in page.text_content("#dialogExtra")
    page.click("#dialogOk")
    page.locator(".banner.notice", has_text="Undid 2 file changes").wait_for()
    wait_idle(page)
    assert "a - b" in (server.repo / "agent/core.py").read_text()
    assert "# 1 + 2" not in (server.repo / "tests/test_core.py").read_text()
    assert statuses(server, session) == ["reverted", "reverted"]


def test_unticking_rewinds_the_conversation_but_keeps_the_files(page, server, session):
    two_applied_changes(page, server)
    msg = page.locator(".msg.user", has_text="fix two")
    msg.hover()
    msg.locator("[data-act=retry]").click()
    page.locator("#dialogTitle", has_text="Retry from here?").wait_for()  # the last message asks now: it has changes
    page.uncheck("#cpRestore")
    page.click("#dialogOk")
    wait_idle(page)
    assert "a + b" in (server.repo / "agent/core.py").read_text()
    assert "reverted" not in statuses(server, session)


def test_undo_file_changes_from_here_keeps_the_conversation(page, server, session):
    two_applied_changes(page, server)
    send(page, "hello again")
    wait_idle(page)
    later = page.locator(".msg.user", has_text="hello again")
    later.hover()
    page.wait_for_timeout(300)  # its preview arrives: nothing was applied from here on
    assert later.locator("[data-act=undo]").is_hidden()
    first = page.locator(".msg.user", has_text="fix two")
    first.hover()
    first.locator("[data-act=undo]").click()
    page.locator("#dialogTitle", has_text="Undo file changes from here?").wait_for()
    assert page.locator("#dialogExtra .cp-row").count() == 2
    page.click("#dialogOk")
    page.locator(".banner.notice", has_text="Undid 2 file changes").wait_for()
    assert "a - b" in (server.repo / "agent/core.py").read_text()
    page.wait_for_function("() => [...document.querySelectorAll('.card[data-prop] .status')]"
                           ".every((s) => s.textContent === 'reverted')")
    assert page.locator(".msg.user", has_text="hello again").count() == 1  # the conversation stays
    assert statuses(server, session) == ["reverted", "reverted"]


def test_a_file_changed_since_is_listed_and_left_as_is(page, server, session):
    two_applied_changes(page, server)
    core = server.repo / "agent/core.py"
    core.write_text(core.read_text() + "# my own edit\n")
    msg = page.locator(".msg.user", has_text="fix two")
    msg.hover()
    msg.locator("[data-act=undo]").click()
    left = page.locator("#dialogExtra .cp-row.left")
    left.wait_for()
    assert "agent/core.py" in left.text_content() and "changed since it was applied" in left.text_content()
    page.click("#dialogOk")
    notice = page.locator(".banner.notice", has_text="Undid 1 file change")
    notice.wait_for()
    assert "left 1 as is: agent/core.py #1 (changed since it was applied)" in notice.text_content()
    assert core.read_text().endswith("# my own edit\n")  # never overwritten
    assert "# 1 + 2" not in (server.repo / "tests/test_core.py").read_text()


def test_when_undoing_fails_the_conversation_is_shown_as_it_still_is(page, server, session):
    two_applied_changes(page, server)
    send(page, "hello again")
    wait_idle(page)
    core = server.repo / "agent/core.py"
    core.chmod(0o444)
    try:
        first = page.locator(".msg.user", has_text="fix two")
        first.hover()
        first.locator("[data-act=retry]").click()
        page.locator("#dialogTitle", has_text="Retry from here?").wait_for()
        page.click("#dialogOk")
        page.locator(".toast.err", has_text="The conversation wasn't rewound").wait_for()
    finally:
        core.chmod(0o644)
    page.locator(".msg.user", has_text="hello again").wait_for()  # redrawn as the server kept it
    assert page.locator(".msg.user", has_text="fix two").count() == 1
    assert "a + b" in core.read_text() and statuses(server, session) == ["applied", "reverted"]


def model_calls(server):
    return [c for c in server.llm.calls if "messages" in c]


def test_if_the_changes_cant_be_checked_retry_stops_instead_of_skipping_the_question(page, server, session):
    two_applied_changes(page, server)
    calls = len(model_calls(server))
    page.route("**/checkpoint?*", lambda route: route.fulfill(status=500, json={"error": "database is locked"}))
    page.expected_errors.append("500 (Internal Server Error)")
    msg = page.locator(".msg.user", has_text="fix two")
    msg.hover()
    msg.locator("[data-act=retry]").click()  # the last message: without changes it would rewind straight away
    page.locator(".toast.err", has_text="database is locked").wait_for()
    assert page.locator("#dialog").is_hidden() and len(model_calls(server)) == calls
    assert statuses(server, session) == ["applied", "applied"]


def _held(page, pattern, method):
    """Hold back `method` requests matching `pattern` until the test lets them go; others pass straight through
    (hovering a message fetches the same checkpoint with GET, which Retry also uses)."""
    held = []

    def handle(route):
        if route.request.method == method and not held:
            held.append(route)
        else:
            route.continue_()

    page.route(pattern, handle)
    return held


def test_switching_sessions_while_the_changes_load_cancels_the_retry(page, server, session):
    two_applied_changes(page, server)
    send(page, "hello again")
    wait_idle(page)
    before = len(server.store.messages(session.id))
    first = page.locator(".msg.user", has_text="fix two")
    first.hover()
    page.wait_for_function("() => !document.querySelector('.msg.user [data-act=undo]')?.hidden")  # hover check done
    held = _held(page, "**/checkpoint?*", "GET")
    with page.expect_request("**/checkpoint?*"):
        first.locator("[data-act=retry]").click()
    page.click("#newChatBtn")
    page.wait_for_function("() => !document.querySelector('.msg.user')")
    with page.expect_response("**/checkpoint?*"):
        held[0].continue_()
    page.wait_for_timeout(300)  # the late answer must not open a dialog for the other session
    assert page.locator("#dialog").is_hidden() and page.locator(".msg.user").count() == 0
    assert len(server.store.messages(session.id)) == before  # the original session wasn't rewound either


def test_switching_sessions_while_undoing_keeps_the_result_out_of_the_other_session(page, server, session):
    two_applied_changes(page, server)
    held = _held(page, "**/restore", "POST")
    first = page.locator(".msg.user", has_text="fix two")
    first.hover()
    first.locator("[data-act=undo]").click()
    page.locator("#dialogTitle", has_text="Undo file changes from here?").wait_for()
    with page.expect_request("**/restore"):
        page.click("#dialogOk")
    page.click("#newChatBtn")
    page.wait_for_function("() => !document.querySelector('.msg.user')")
    with page.expect_response("**/restore"):
        held[0].continue_()
    page.wait_for_timeout(300)
    assert page.locator(".banner.notice").count() == 0  # nothing from the other session lands here
    assert statuses(server, session) == ["reverted", "reverted"]  # the undo itself still happened
