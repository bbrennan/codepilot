"""TEMPORARY diagnostic for #137, removed before it merges: the editor's place is sometimes not restored on CI's
Linux runners (the top line is still 1 five seconds after switching back). Repeats the switch at the end of the suite
and, when it fails, reports every showLine call and scroll event on the editor's scroller."""

import pytest
from test_code_editor_ui import edit
from uihelpers import EDITOR, SCROLLER, editor_top_line, wait_editor

WATCH = """() => { window.__log = []; const sl = window.showLine;
  window.showLine = (el, n) => {
    window.__log.push(['showLine', n, 'sh', el.scrollHeight, 'ch', el.clientHeight, 'conn', el.isConnected,
                       't', Math.round(performance.now())]);
    sl(el, n); window.__log.push(['set', el.scrollTop]);
    if (!el.__w) { el.__w = 1; el.addEventListener('scroll', () => window.__log.push(['scroll', el.scrollTop,
      'sh', el.scrollHeight, 't', Math.round(performance.now())])); }
  }; }"""


@pytest.mark.parametrize("i", range(25))
def test_probe_editor_place(page, server, session, i):
    edit(page, server, "long.py", "".join(f"value_{n} = {n}\n" for n in range(1, 301)))
    page.keyboard.press("Control+g")
    page.locator("#codeEdit input").first.wait_for()
    page.keyboard.type("150")
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.activeElement?.isContentEditable")
    top = editor_top_line(page)
    page.evaluate("openFile('agent/core.py')")
    page.locator("#editor .code-view").wait_for()
    tab_top = page.evaluate("() => state.tabs.find((t) => t.id === 'file:long.py').topLine")
    page.evaluate(WATCH)
    page.locator("#editorTabs [data-tab='file:long.py']").click()
    wait_editor(page)
    try:
        page.wait_for_function(f"(n) => Math.floor(({SCROLLER})(document.querySelector('{EDITOR}')).scrollTop / 20) + 1"
                               " === n", arg=top, timeout=5000)
    except Exception:
        now = page.evaluate("() => state.tabs.find((t) => t.id === 'file:long.py').topLine")
        raise AssertionError(f"PROBE read {top}; tab.topLine before switching {tab_top}, after {now}; now showing "
                             f"{editor_top_line(page)}; log {page.evaluate('window.__log')}") from None
