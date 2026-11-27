"""Edit mode's editor (spec code-editor): CodeMirror, loaded on the first Edit. Tests reach it through the helpers in
uihelpers.py, never through CodeMirror's own DOM, except the few that look at highlighting."""

import sys

import pytest
from test_keyboard_access_ui import audit
from uihelpers import (editor_caret_line, editor_has_focus, editor_open, editor_text, editor_top_line, focus_editor,
                       open_app, type_in_editor, wait_editor)

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
    matched = page.evaluate("() => [...document.querySelectorAll('#codeEdit .cm-matchingBracket')]"
                            ".map((e) => e.textContent)")
    assert matched == ["(", ")"], matched


def test_several_cursors_type_at_once(page, server, session):
    edit(page, server, "calc.py", "a = 1\nb = 2\n")
    page.keyboard.press("Alt+ControlOrMeta+ArrowDown" if sys.platform == "darwin" else "Control+Alt+ArrowDown")
    page.keyboard.type("# ")
    assert editor_text(page) == "# a = 1\n# b = 2\n"


# -- task 2.4: the app's colours ---------------------------------------------------------------------------------------

# A token as the page resolves it, as a colour or a background.
TOKEN = """([name, prop]) => { const p = document.createElement('i'); p.style[prop] = `var(${name})`;
  document.body.append(p); const c = getComputedStyle(p)[prop]; p.remove(); return c; }"""
# What the editor draws, by geometry (the line numbers at x 10, the text further right) and, for the keyword, its span.
LOOK = """() => { const r = document.querySelector('#codeEdit').getBoundingClientRect();
  const at = (x, y) => document.elementFromPoint(r.left + x, r.top + y);
  const bg = (el) => { while (el && getComputedStyle(el).backgroundColor === 'rgba(0, 0, 0, 0)') el = el.parentElement;
    return el && getComputedStyle(el).backgroundColor; };
  const kw = [...document.querySelectorAll('#codeEdit [contenteditable] span')].find((s) => s.textContent === 'def');
  return { background: bg(at(r.width - 40, 56)), gutter: bg(at(10, 56)), number: getComputedStyle(at(10, 56)).color,
    text: getComputedStyle(at(r.width - 40, 56).closest('[contenteditable]')).color,
    keyword: getComputedStyle(kw).color }; }"""


def tokens(page):
    t = lambda name, prop="color": page.evaluate(TOKEN, [name, prop])  # noqa: E731
    return {"background": t("--bg-2", "backgroundColor"), "gutter": t("--bg-2", "backgroundColor"),
            "number": t("--faint"), "text": t("--fg"), "keyword": t("--syn-kw")}


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_editor_draws_with_the_apps_tokens_and_follows_the_theme_toggle(page, server, session, theme):
    page.add_init_script(f"try {{ localStorage.setItem('cp-theme', '{theme}') }} catch {{}}")
    edit(page, server, "calc.py", "def total(xs):\n    return sum(xs)\n\n\n")
    assert page.evaluate(LOOK) == tokens(page)
    first = page.evaluate(LOOK)
    page.click("#themeBtn")  # while the editor is open
    page.wait_for_function("(t) => document.documentElement.dataset.theme !== t", arg=theme)
    assert page.evaluate(LOOK) == tokens(page) and page.evaluate(LOOK) != first


# Where line n's number starts, in px below the top of the editor (scanning down the line numbers, by geometry).
NUMBER_AT = """(n) => { const r = document.querySelector('#codeEdit').getBoundingClientRect();
  for (let y = 0; y < r.height; y++) {
    if (document.elementFromPoint(r.left + 10, r.top + y)?.textContent === String(n)) return y;
  }
  return null; }"""


def test_a_line_is_at_the_same_height_in_the_view_and_the_editor(page, server, session):
    edit(page, server, "long.py", "".join(f"value_{i} = {i}\n" for i in range(1, 301)))
    page.click("#fDone")
    page.evaluate("() => { const s = document.querySelector('#edScroll'); s.scrollTop = 119 * 20;"
                  " s.dispatchEvent(new Event('scroll')); }")
    in_view = page.evaluate("""() => document.querySelector('#gutter [data-ln="120"]').getBoundingClientRect().top
      - document.querySelector('#edScroll').getBoundingClientRect().top""")
    page.click("#fEdit")
    wait_editor(page)
    page.evaluate("() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")  # (laid out)
    assert abs(page.evaluate(NUMBER_AT, 120) - in_view) <= 1  # the same line at the same height, not only the same top


# -- task 3.1: find and replace, go to line ---------------------------------------------------------------------------

# The find panel by what a person reads on it (its boxes' names, its buttons' words), not by CodeMirror's classes.
FIND = "#codeEdit input[aria-label='Find']"
REPLACE = "#codeEdit input[aria-label='Replace']"


def find_button(page, label):
    return page.locator("#codeEdit button", has_text=label).first


def type_into(page, sel, text):
    """Type over what a box of the find panel holds, as a person does (it takes the query as keys come up)."""
    page.locator(sel).click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type(text)


def find_option(page, label):
    return page.locator("#codeEdit label", has_text=label).locator("input")


# Whether the last key pressed had its default prevented (the browser's own find, or Chrome's Ctrl+G, didn't run).
WATCH_KEYS = """() => { window.__keys = [];
  addEventListener('keydown', (e) => window.__keys.push([e.key, e.defaultPrevented])); }"""




def selected(page):
    return page.evaluate("() => getSelection().toString()")


def test_mod_f_finds_inside_the_editor_and_enter_goes_to_the_next_and_previous_match(page, server, session):
    edit(page, server, "calc.py", "total = 1\nx = total\ny = 2\nTotal = total + x\n")
    page.evaluate(WATCH_KEYS)
    page.keyboard.press("ControlOrMeta+f")
    page.locator(FIND).wait_for()
    assert page.evaluate("() => window.__keys.at(-1)") == ["f", True]  # not the browser's find
    assert page.evaluate("(s) => document.activeElement === document.querySelector(s)", FIND)
    page.keyboard.type("total")
    page.keyboard.press("Enter")  # the match at the caret first, then on
    assert editor_caret_line(page) == 1
    page.keyboard.press("Enter")
    assert editor_caret_line(page) == 2
    page.keyboard.press("Enter")
    assert editor_caret_line(page) == 4
    page.keyboard.press("Shift+Enter")
    assert editor_caret_line(page) == 2
    page.keyboard.press("Escape")  # closes, back to the text where the match is
    page.locator(FIND).wait_for(state="detached")
    assert editor_has_focus(page) and editor_caret_line(page) == 2


def test_match_case_whole_word_and_regular_expression(page, server, session):
    edit(page, server, "calc.py", "total = 1\ntotals = 2\nTotal = 3\nt0tal = 4\n")
    page.keyboard.press("ControlOrMeta+f")
    type_into(page, FIND, "total")

    def lines():
        page.locator(FIND).press("Enter")
        first = editor_caret_line(page)
        seen = [first]
        for _ in range(4):
            page.locator(FIND).press("Enter")
            if editor_caret_line(page) == first:
                break
            seen.append(editor_caret_line(page))
        return sorted(seen)

    assert lines() == [1, 2, 3]  # any case, inside words
    find_option(page, "match case").check()
    assert lines() == [1, 2]
    find_option(page, "whole word").check()
    assert lines() == [1]
    find_option(page, "match case").uncheck()
    find_option(page, "whole word").uncheck()
    find_option(page, "regular expression").check()
    type_into(page, FIND, r"t\dtal")
    assert lines() == [4]


def test_replace_and_replace_all_are_one_undo_each(page, server, session):
    edit(page, server, "calc.py", "a = old\nb = old\nc = old\n")
    page.keyboard.press("ControlOrMeta+f")
    type_into(page, FIND, "old")
    page.locator(FIND).press("Enter")  # on the first match: Replace replaces what's selected, then moves on
    type_into(page, REPLACE, "new")
    find_button(page, "replace").click()
    assert editor_text(page) == "a = new\nb = old\nc = old\n"
    find_button(page, "replace all").click()
    assert editor_text(page) == "a = new\nb = new\nc = new\n" and dirty(page)
    page.keyboard.press("Escape")
    focus_editor(page)
    page.keyboard.press("ControlOrMeta+z")  # replace all, at once
    assert editor_text(page) == "a = new\nb = old\nc = old\n"
    page.keyboard.press("ControlOrMeta+z")  # the one replace
    assert editor_text(page) == "a = old\nb = old\nc = old\n" and not dirty(page)


def test_ctrl_g_goes_to_a_line(page, server, session):
    edit(page, server, "long.py", "".join(f"value_{i} = {i}\n" for i in range(1, 301)))
    page.evaluate(WATCH_KEYS)
    page.keyboard.press("Control+g")  # as in VS Code, on a Mac too
    box = page.locator("#codeEdit input").first
    box.wait_for()
    assert page.evaluate("() => window.__keys.at(-1)") == ["g", True]  # not the browser's find next
    page.keyboard.type("240")
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.activeElement?.isContentEditable")
    assert editor_caret_line(page) == 240 and editor_has_focus(page)
    top = editor_top_line(page)
    assert top <= 240 < top + 25  # in view


@pytest.mark.parametrize("size", [(1024, 700), (1440, 900)])
def test_the_find_panel_fits_inside_the_editor(page, server, session, size):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    edit(page, server, "calc.py", "a = 1\n")
    page.keyboard.press("ControlOrMeta+f")
    page.locator(FIND).wait_for()
    outside = page.evaluate("""() => { const box = document.querySelector('#codeEdit').getBoundingClientRect();
      return [...document.querySelectorAll('#codeEdit input, #codeEdit button, #codeEdit label')].filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width && (r.left < box.left - 0.5 || r.right > box.right + 0.5 || r.top < box.top - 0.5
          || r.bottom > box.bottom + 0.5); }).map((el) => el.outerHTML.slice(0, 80)); }""")
    width = page.evaluate("() => document.querySelector('#codeEdit').getBoundingClientRect().width")
    assert not outside, (width, outside)


# -- task 3.2: place, drafts, read-only, large files -------------------------------------------------------------------


def test_switching_tabs_keeps_the_editors_caret_and_top_line(page, server, session):
    edit(page, server, "long.py", "".join(f"value_{i} = {i}\n" for i in range(1, 301)))
    page.keyboard.press("Control+g")
    page.locator("#codeEdit input").first.wait_for()
    page.keyboard.type("150")
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.activeElement?.isContentEditable")
    top = editor_top_line(page)
    page.evaluate("openFile('agent/core.py')")
    page.locator("#editor .code-view").wait_for()
    page.locator("#editorTabs [data-tab='file:long.py']").click()
    wait_editor(page)
    assert editor_caret_line(page) == 150 and editor_top_line(page) == top


def test_the_editors_caret_and_draft_come_back_after_a_reload(page, server, session):
    edit(page, server, "long.py", "".join(f"value_{i} = {i}\n" for i in range(1, 301)))
    page.keyboard.press("Control+g")
    page.locator("#codeEdit input").first.wait_for()
    page.keyboard.type("90")
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.activeElement?.isContentEditable")
    page.keyboard.type("# here ")
    page.wait_for_timeout(500)  # (stored)
    page.reload()
    wait_editor(page)
    assert editor_caret_line(page) == 90 and "value_89 = 89\n# here value_90" in editor_text(page)
    assert dirty(page)


def test_a_two_megabyte_file_opens_in_the_editor_within_a_second_and_scrolls(page, server, session):
    line = "x" * 40 + " = 'some value'  # a comment\n"
    (server.repo / "big.py").write_text(line * (1_990_000 // len(line)))
    open_app(page)
    edit_core(page)  # the bundle loaded: what's timed is the editor, not the network
    page.click("#fDone")
    # Timed in the page around the mount, to the frame after it's laid out (not from the click: the file's own fetch and
    # the read view are the same as before).
    page.evaluate("""() => { const mount = window.mountEditor; window.mountEditor = (...args) => {
      const t0 = performance.now(), ed = mount(...args);
      requestAnimationFrame(() => requestAnimationFrame(() => { window.__mounted = performance.now() - t0; }));
      return ed; }; }""")
    page.evaluate("openFile('big.py')")
    page.locator("#fEdit").click()
    page.wait_for_function("() => window.__mounted !== undefined", timeout=20_000)
    took = page.evaluate("window.__mounted")
    # 1 s is the requirement; this Mac takes a fraction of it, and CI's runners are slower (see the PR).
    assert took < 1000, f"{took:.0f} ms"
    scrolled = page.evaluate("""() => new Promise((done) => { const host = document.querySelector('#codeEdit');
      const el = [...host.querySelectorAll('*')].find((e) => /auto|scroll/.test(getComputedStyle(e).overflowY));
      const t0 = performance.now(); el.scrollTop = el.scrollHeight / 2;
      requestAnimationFrame(() => requestAnimationFrame(() => done(performance.now() - t0))); })""")
    assert scrolled < 250, f"{scrolled:.0f} ms to draw the middle of the file"
    page.keyboard.press("ControlOrMeta+End")
    page.keyboard.type("# end")
    assert editor_text(page).endswith("# end") and dirty(page)


def test_find_cannot_replace_while_the_folders_change(page, server, session):
    held = []
    page.route(f"**/api/sessions/{session.id}",
               lambda r: held.append(r) if r.request.method == "PATCH" else r.continue_())
    open_app(page)
    edit_core(page)
    before = editor_text(page)
    page.evaluate("() => { setFolders({ folders: [] }); }")  # held: the change is on its way (not awaited)
    page.wait_for_function("() => state.changingFolders")
    focus_editor(page)
    page.keyboard.press("ControlOrMeta+f")
    type_into(page, FIND, "a")
    assert page.locator(REPLACE).count() == 0  # find, but no replacing in a locked editor
    page.locator(FIND).press("Enter")
    assert editor_text(page) == before and not dirty(page)
    held[0].continue_()
