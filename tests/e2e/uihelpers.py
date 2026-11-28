"""Helpers for the browser tests."""


def open_app(page, wait_tree=True):
    # A first visit shows Sessions; these tests start from the Explorer, as someone who has chosen it would.
    # (try: about:blank, which some tests visit, has no storage)
    page.add_init_script("try { localStorage.getItem('cp-view') ?? localStorage.setItem('cp-view', 'explorer') } catch {}")
    page.goto("/")
    page.wait_for_function("() => document.querySelector('#sbProvider')?.textContent.length > 0")
    if wait_tree:
        page.locator("#tree [data-file], #tree [data-dir]").first.wait_for()
    return page


# -- Edit mode's editor ------------------------------------------------------------------------------------------------
# Tests reach the editor through these: #codeEdit (its host, which keeps that id), the handle editor.js gives app.js
# (codeEditor()), and what any editor has, never CodeMirror's own DOM, so the editor can change without its tests. The
# scroller is found by its style, not its class. Each waits for the editor first: it loads on the first Edit.

EDITOR = "#codeEdit"
SCROLLER = ("(host) => [host, ...host.querySelectorAll('*')]"
            ".find((el) => /auto|scroll/.test(getComputedStyle(el).overflowY))")


def wait_editor(page):
    """Edit mode is open and the editor is ready to type in (it loads on the first Edit)."""
    page.locator(EDITOR).wait_for()
    page.wait_for_function("() => codeEditor()?.owns(document.querySelector('#codeEdit [contenteditable]'))")


def editor_open(page):
    return page.locator(EDITOR).count() > 0


def editor_text(page):
    wait_editor(page)
    return page.evaluate("() => codeEditor().text()")


def set_editor_text(page, text):
    """Replace the whole text, as typing over a selection of all of it would."""
    wait_editor(page)
    page.evaluate("(t) => codeEditor().setText(t)", text)


def focus_editor(page):
    """Put focus in the text, keeping the caret where it was."""
    wait_editor(page)
    page.evaluate("() => codeEditor().focus()")


def editor_has_focus(page):
    """Focus is in the text (not in a panel of the editor's, nor anywhere else)."""
    return page.eval_on_selector(EDITOR, """(host) => { const a = document.activeElement;
      return !!a && (a === host || host.contains(a)) && (a.isContentEditable || a.tagName === 'TEXTAREA'); }""")


def click_editor(page):
    """A real click in the text (Chrome counts a page as used only after one)."""
    wait_editor(page)
    page.click(EDITOR)


def type_in_editor(page, text):
    focus_editor(page)
    page.keyboard.type(text)


def press_in_editor(page, key):
    focus_editor(page)
    page.keyboard.press(key)


def editor_caret_line(page):
    wait_editor(page)
    return page.evaluate("() => { const ed = codeEditor(); return ed.text().slice(0, ed.place().caret)"
                         ".split('\\n').length; }")


def editor_top_line(page):
    """The line at the top of the editor, from its scroll position: it draws 20px lines, as the read view does."""
    wait_editor(page)
    return page.eval_on_selector(EDITOR, f"(host) => Math.floor(({SCROLLER})(host).scrollTop / 20) + 1")


def wait_editor_top_line(page, n):
    """The editor comes to show line n at its top. A mount puts its place back in CodeMirror's next measure, a frame
    after the editor is ready, so a read straight after wait_editor can see line 1 on a slow runner."""
    wait_editor(page)
    try:
        page.wait_for_function(f"(n) => Math.floor(({SCROLLER})(document.querySelector('{EDITOR}')).scrollTop / 20) + 1"
                               " === n", arg=n, timeout=5000)
    except Exception:  # the editor settled somewhere else: say where (no assert rewriting in a helper module)
        raise AssertionError(f"the editor's top line is {editor_top_line(page)}, not {n}") from None


def scroll_editor_to_line(page, n):
    wait_editor(page)
    page.eval_on_selector(EDITOR, f"""(host, n) => {{ const el = ({SCROLLER})(host); el.scrollTop = (n - 1) * 20;
      el.dispatchEvent(new Event('scroll')); }}""", n)
