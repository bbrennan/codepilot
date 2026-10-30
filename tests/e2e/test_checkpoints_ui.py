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
    page.locator(".banner.notice", has_text="Undid 1 file change").wait_for()
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
