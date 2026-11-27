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


# -- task 2.3: languages, line numbers, indentation, brackets, history -------------------------------------------------


def edit(page, server, name, text):
    (server.repo / name).write_text(text)
    open_app(page)
    page.evaluate("(p) => openFile(p)", name)
    page.locator("#fEdit").click()
    wait_editor(page)


# Highlighting is the one thing looked at in CodeMirror's own DOM: the coloured spans in the text.
SPANS = "() => document.querySelectorAll('#codeEdit [contenteditable] span').length"

# What's drawn at a point of the editor, by geometry: the text at (x, y) from its top-left corner.
AT = """([x, y]) => { const r = document.querySelector('#codeEdit').getBoundingClientRect();
  return document.elementFromPoint(r.left + x, r.top + y)?.textContent; }"""
# The background of the text's row at y (the line under the point, past the line numbers).
ROW_BG = """(y) => { const r = document.querySelector('#codeEdit').getBoundingClientRect();
  let el = document.elementFromPoint(r.right - 40, r.top + y);
  while (el && getComputedStyle(el).backgroundColor === 'rgba(0, 0, 0, 0)') el = el.parentElement;
  return el && getComputedStyle(el).backgroundColor; }"""


@pytest.mark.parametrize("name, text", [
    ("calc.py", "def total(xs):\n    return sum(xs)  # all of them\n"),
    ("view.tsx", "const n: number = 1;\nexport const V = () => <div>{n}</div>;\n"),
])
def test_code_is_highlighted_as_the_read_view_highlights_it(page, server, session, name, text):
    edit(page, server, name, text)
    assert page.evaluate(SPANS) > 3


def test_plain_text_is_not_highlighted(page, server, session):
    edit(page, server, "notes.txt", "def total(xs): return 1  # not code\n")
    assert page.evaluate(SPANS) == 0


def test_every_language_the_read_view_knows_has_an_answer_in_the_editor(page, server, session):
    open_app(page)
    edit_core(page)  # (the bundle loaded)
    missing = page.evaluate("() => Object.keys(LANGS).filter((ext) => !(ext in LANG_FOR))")
    unknown = page.evaluate("() => Object.values(LANG_FOR).filter((name) => name && !CM.languages[name])")
    assert missing == [] and unknown == [], (missing, unknown)


def test_line_numbers_and_the_caret_line_are_shown(page, server, session):
    edit(page, server, "calc.py", "".join(f"x{i} = {i}\n" for i in range(1, 11)))
    assert page.evaluate(AT, [10, 16]) == "1" and page.evaluate(AT, [10, 36]) == "2"  # 6px, then 20px a line
    caret_row, other_row = page.evaluate(ROW_BG, 16), page.evaluate(ROW_BG, 56)
    assert caret_row != other_row  # the caret's line is marked
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    assert page.evaluate(ROW_BG, 56) == caret_row and page.evaluate(ROW_BG, 16) == other_row


def test_enter_keeps_the_indent_and_indents_after_a_block_opens(page, server, session):
    edit(page, server, "calc.py", "def total(xs):\n")
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    page.keyboard.type("return 1")
    assert editor_text(page) == "def total(xs):\n    return 1\n"


def test_enter_after_a_tab_indented_line_indents_with_a_tab(page, server, session):
    edit(page, server, "tabs.py", "if x:\n\ty = 1\n")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    page.keyboard.type("z = 2")
    assert editor_text(page) == "if x:\n\ty = 1\n\tz = 2\n"


def test_tab_and_shift_tab_indent_and_dedent_the_selected_lines(page, server, session):
    edit(page, server, "calc.py", "a = 1\nb = 2\nc = 3\nd = 4\n")
    page.keyboard.press("Shift+ArrowDown")
    page.keyboard.press("Shift+ArrowDown")
    page.keyboard.press("Shift+End")  # lines 1-3
    page.keyboard.press("Tab")
    assert editor_text(page) == "    a = 1\n    b = 2\n    c = 3\nd = 4\n"
    page.keyboard.press("Shift+Tab")
    assert editor_text(page) == "a = 1\nb = 2\nc = 3\nd = 4\n"


def test_a_tab_indented_file_indents_with_tabs(page, server, session):
    edit(page, server, "tabs.py", "if x:\n\ty = 1\n")
    page.keyboard.press("Shift+ArrowDown")
    page.keyboard.press("Tab")
    assert editor_text(page) == "\tif x:\n\ty = 1\n"


def test_undo_and_redo_are_the_editors_own(page, server, session):
    edit(page, server, "calc.py", "a = 1\n")
    page.keyboard.type("b = 2")  # one step (a new line starts another, as in other editors)
    page.keyboard.press("ControlOrMeta+z")
    assert editor_text(page) == "a = 1\n" and not dirty(page)
    page.keyboard.press("ControlOrMeta+Shift+z")
    assert editor_text(page) == "b = 2a = 1\n" and dirty(page)


def test_a_bracket_shows_its_match(page, server, session):
    edit(page, server, "calc.py", "total(a, (b + c))\n")
    page.keyboard.press("ArrowRight")
    for _ in range(5):
        page.keyboard.press("ArrowRight")  # after "total("
    matched = page.evaluate("() => [...document.querySelectorAll('#codeEdit .cm-matchingBracket')].map((e) => e.textContent)")
    assert matched == ["(", ")"], matched


def test_several_cursors_type_at_once(page, server, session):
    edit(page, server, "calc.py", "a = 1\nb = 2\n")
    page.keyboard.press("Alt+ControlOrMeta+ArrowDown" if sys.platform == "darwin" else "Control+Alt+ArrowDown")
    page.keyboard.type("# ")
    assert editor_text(page) == "# a = 1\n# b = 2\n"

