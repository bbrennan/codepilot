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
# Tests reach the editor through these, by #codeEdit (its host, which keeps that id) and what any editor has, never by
# how it's built, so the editor can change without its tests. The scroller is found by its style, not its class.

EDITOR = "#codeEdit"
SCROLLER = "(host) => [host, ...host.querySelectorAll('*')].find((el) => /auto|scroll/.test(getComputedStyle(el).overflowY))"


def wait_editor(page):
    """Edit mode is open and the editor is ready to type in."""
    page.locator(EDITOR).wait_for()


def editor_open(page):
    return page.locator(EDITOR).count() > 0


def editor_text(page):
    return page.input_value(EDITOR)


def set_editor_text(page, text):
    """Replace the whole text, as typing over a selection of all of it would."""
    page.fill(EDITOR, text)


def focus_editor(page):
    """Put focus in the text, keeping the caret where it was."""
    page.focus(EDITOR)


def click_editor(page):
    """A real click in the text (Chrome counts a page as used only after one)."""
    page.click(EDITOR)


def type_in_editor(page, text):
    focus_editor(page)
    page.keyboard.type(text)


def press_in_editor(page, key):
    focus_editor(page)
    page.keyboard.press(key)


def editor_caret_line(page):
    return page.eval_on_selector(EDITOR, "(t) => t.value.slice(0, t.selectionStart).split('\\n').length")


def editor_top_line(page):
    """The line at the top of the editor, from its scroll position: it draws 20px lines, as the read view does."""
    return page.eval_on_selector(EDITOR, f"(host) => Math.floor(({SCROLLER})(host).scrollTop / 20) + 1")


def scroll_editor_to_line(page, n):
    page.eval_on_selector(EDITOR, f"""(host, n) => {{ const el = ({SCROLLER})(host); el.scrollTop = (n - 1) * 20;
      el.dispatchEvent(new Event('scroll')); }}""", n)
