"""Edit mode's editor (spec code-editor): CodeMirror, loaded on the first Edit. Tests reach it through the helpers in
uihelpers.py, never through CodeMirror's own DOM, except the few that look at highlighting."""

import sys

import pytest
from test_keyboard_access_ui import audit
from uihelpers import editor_has_focus, editor_open, editor_text, focus_editor, open_app, type_in_editor, wait_editor

BUNDLE = "**/static/vendor/codemirror.min.js"


def mod(page):
    return "Meta" if page.evaluate("navigator.platform").startswith("Mac") else "Control"


def dirty(page):
    return page.evaluate("() => document.querySelector('.tab.on').classList.contains('dirty')")


def edit_core(page):
    page.evaluate("openFile('agent/core.py')")
    page.locator("#fEdit").click()
    wait_editor(page)


# -- task 2.2: the editor in place of the textarea ---------------------------------------------------------------------


def test_the_editor_loads_on_the_first_edit_and_only_then(page, server, session):
    fetched = []
    page.on("request", lambda r: fetched.append(r.url) if r.url.endswith("/codemirror.min.js") else None)
    open_app(page)
    page.evaluate("openFile('agent/core.py')")
    page.locator("#editor .code-view").wait_for()
    assert fetched == []  # a session that never edits never pays for it
    page.click("#fEdit")
    wait_editor(page)
    page.click("#fDone")
    page.click("#fEdit")
    wait_editor(page)
    assert len(fetched) == 1


def test_typing_marks_the_tab_unsaved_mod_s_saves_and_done_goes_back(page, server, session):
    core = server.repo / "agent" / "core.py"
    original = core.read_text()
    open_app(page)
    edit_core(page)
    page.click("#fDone")  # nothing typed: no question
    page.locator("#editor .code-view").wait_for()
    assert not editor_open(page)

    page.click("#fEdit")
    wait_editor(page)
    assert editor_has_focus(page)  # Edit puts you in the text
    page.keyboard.type("# mine\n")  # at the top: where you were reading
    page.wait_for_function("() => document.querySelector('.tab.on').classList.contains('dirty')")
    assert page.locator("#edState").text_content() == "Unsaved changes"
    page.keyboard.press(f"{mod(page)}+s")
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    assert core.read_text() == "# mine\n" + original
    assert editor_text(page) == "# mine\n" + original

    type_in_editor(page, "x")  # back to exactly the file: not unsaved
    assert dirty(page)
    page.keyboard.press("Backspace")
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")


def test_done_asks_before_discarding_and_cancel_puts_you_back_in_the_text(page, server, session):
    core = server.repo / "agent" / "core.py"
    original = core.read_text()
    open_app(page)
    edit_core(page)
    page.keyboard.type("# draft\n")
    page.click("#fDone")
    page.locator("#dialogTitle", has_text="Discard changes to core.py").wait_for()
    page.click("#dialogCancel")
    page.wait_for_function("() => document.querySelector('#dialog').hidden")
    page.wait_for_timeout(50)  # (a dialog gives focus back after the key or click that closed it)
    assert editor_has_focus(page)  # since #131 focus goes back to what opened a dialog: here that's the text
    page.keyboard.type("more ")
    assert editor_text(page).startswith("# draft\nmore ")

    page.click("#fDone")
    page.click("#dialogOk")  # Discard
    page.locator("#editor .code-view").wait_for()
    assert core.read_text() == original and not dirty(page)


def test_a_blocked_editor_says_so_and_leaves_the_file_shown(page, server, session):
    page.expected_errors.append("Failed to load resource")
    page.route(BUNDLE, lambda r: r.abort())
    open_app(page)
    page.evaluate("openFile('agent/core.py')")
    page.click("#fEdit")
    page.locator(".toast.err", has_text="The editor couldn't load").wait_for()
    page.locator("#editor .code-view").wait_for()  # the read view, as it was
    assert not editor_open(page)
    assert page.evaluate("() => state.tabs.find((t) => t.id === state.active).editing") is False

    page.unroute(BUNDLE)  # the next Edit tries again
    page.click("#fEdit")
    wait_editor(page)


# -- the app's keys, with focus in the editor ------------------------------------------------------------------------


def test_mod_enter_in_the_editor_approves_a_waiting_command_and_leaves_the_text_alone(page, server, session):
    open_app(page)
    edit_core(page)
    before = editor_text(page)
    page.fill("#input", "run ls")
    page.press("#input", "Enter")
    page.locator("#reviewBar .rb-approval").wait_for()
    focus_editor(page)
    page.keyboard.press("ControlOrMeta+Enter")
    page.locator("#reviewBar .rb-approval").wait_for(state="hidden")  # approved
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    assert editor_text(page) == before and not dirty(page)  # and no blank line in your file


def test_the_apps_shortcuts_work_from_inside_the_editor(page, server, session):
    open_app(page)
    edit_core(page)
    before = editor_text(page)
    page.keyboard.press("ControlOrMeta+p")  # go to file
    page.locator("#paletteInput").wait_for()
    page.keyboard.press("Escape")
    focus_editor(page)
    page.keyboard.press("ControlOrMeta+Shift+l")  # (the app's ⌘L doesn't look at Shift, so neither may the editor)
    page.wait_for_function("() => document.activeElement === document.querySelector('#input')")
    focus_editor(page)
    page.keyboard.press("ControlOrMeta+l")  # focus the chat
    page.wait_for_function("() => document.activeElement === document.querySelector('#input')")
    focus_editor(page)
    page.keyboard.press("F6")  # the next pane (the panel is closed): the chat
    page.wait_for_function("() => document.activeElement === document.querySelector('#input')")
    assert editor_text(page) == before and not dirty(page)


@pytest.mark.skipif(sys.platform != "darwin", reason="Ctrl+V as paste is a macOS convenience")
def test_ctrl_v_pastes_in_the_editor_on_a_mac(page, server, session):
    open_app(page)
    edit_core(page)
    page.evaluate("() => navigator.clipboard.writeText('pasted = 1\\n')")
    page.keyboard.press("Control+v")  # (CodeMirror's Emacs-style keys would make it page down)
    page.wait_for_function("() => document.querySelector('.tab.on').classList.contains('dirty')")
    assert editor_text(page).startswith("pasted = 1\ndef add")


def test_tab_indents_and_escape_then_tab_leaves_the_editor(page, server, session):
    open_app(page)
    edit_core(page)
    page.keyboard.press("Tab")  # indents: focus stays
    assert editor_has_focus(page) and editor_text(page).startswith("    def add")
    page.keyboard.press("Escape")
    page.keyboard.press("Tab")  # the way out (docs/usage.md)
    assert not editor_has_focus(page)
    assert editor_text(page).startswith("    def add")  # one indent, not two


def test_the_editor_is_one_tab_stop_named_for_its_file_and_nothing_in_it_is_out_of_reach(page, server, session):
    open_app(page)
    edit_core(page)
    # Tab stops: a tabindex of 0 or more, or an editing host (Chrome says -1 for one, but Tab goes there).
    stops = page.evaluate("""() => [...document.querySelectorAll('#codeEdit *, #codeEdit')].filter((el) =>
      (el.tabIndex >= 0 || (el.getAttribute('contenteditable') === 'true' && !el.hasAttribute('tabindex')))
      && el.getClientRects().length).map((el) => el.getAttribute('aria-label'))""")
    assert stops == ["Edit agent/core.py"], stops
    page.focus("#fDone")
    page.keyboard.press("Tab")  # from the bar's last button: into the text
    assert editor_has_focus(page)
    audit(page, "the editor")

