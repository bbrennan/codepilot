"""Approvals that depend on the moment: destructive commands are flagged, and external content pauses saved rules."""

from uihelpers import open_app


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def read_docs(page):
    send(page, "read docs")
    page.locator("#taintChip:not([hidden])").wait_for()
    wait_idle(page)


def test_a_destructive_command_is_flagged_and_offers_no_rule(page, server, session):
    open_app(page)
    send(page, "delete build")
    warning = page.locator("#reviewBar .rb-warn.danger")
    warning.wait_for()
    assert warning.text_content().strip() == "Destructive: deletes files recursively"
    assert page.locator("#rbAllow").count() == 0
    page.click("#rbDeny")


def test_external_content_shows_a_chip_and_pauses_always_allow_until_cleared(page, server, session):
    open_app(page)
    assert page.locator("#taintChip").is_hidden()
    read_docs(page)
    send(page, "run ls")
    reason = page.locator("#reviewBar .rb-warn.caution")
    reason.wait_for()
    assert "external content (docs fastapi)" in reason.text_content() and page.locator("#rbAllow").count() == 0
    page.click("#rbDeny")
    wait_idle(page)
    page.click("#taintChip")
    menu = page.locator("#ctxMenu", has_text="docs fastapi")
    menu.wait_for()
    menu.get_by_text("Clear…").click()
    page.locator("#dialogHint", has_text="checked what it read").wait_for()
    page.click("#dialogOk")
    page.wait_for_function("() => document.querySelector('#taintChip').hidden")
    send(page, "run ls")
    page.locator("#rbAllow").wait_for()  # always allow is back
    assert page.locator("#reviewBar .rb-warn").count() == 0
    page.click("#rbDeny")


def test_the_chip_survives_a_reload(page, server, session):
    open_app(page)
    read_docs(page)
    page.reload()
    page.locator("#taintChip:not([hidden])").wait_for()


def test_memory_shows_saved_rules_as_paused(page, server, session):
    open_app(page)
    send(page, "run ls")
    page.locator("#rbAllow").check()
    page.click("#rbApprove")
    wait_idle(page)
    read_docs(page)
    page.click("[data-view=memory]")
    page.locator("#memoryView .group-head", has_text="paused while this session has external content").wait_for()


def test_the_chip_fits_in_the_chat_header(page, server, session):
    open_app(page)
    read_docs(page)
    box = page.evaluate("""() => { const head = document.querySelector('.chat-head').getBoundingClientRect();
      const inside = (sel) => { const r = document.querySelector(sel).getBoundingClientRect();
        return r.left >= head.left - 1 && r.right <= head.right + 1 && r.width > 0; };
      return { chip: inside('#taintChip'), plus: inside('#newChatBtn'), title: inside('#chatTitle'),
               wide: document.querySelector('.chat-head').scrollWidth <= document.querySelector('.chat-head').clientWidth }; }""")
    assert box == {"chip": True, "plus": True, "title": True, "wide": True}
