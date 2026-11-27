"""Everything by keyboard (spec keyboard-access): rows and links you can click are reachable with Tab and act on
Enter or Space; the tree, tabs, menus and dialogs move with the arrows; what happens is announced.

Keyboard only: after open_app nothing is clicked. What a test needs that isn't under test (a view shown, a session
with changes, a starting point for Tab) is set up through the page's own functions, `page.focus` or the store."""

import pytest
from uihelpers import open_app

ACTIVE = """() => { const a = document.activeElement;
  return !a || a === document.body ? 'body' : a.outerHTML.slice(0, 160); }"""


def focus_is(page, sel):
    return page.evaluate("(s) => !!document.activeElement?.matches(s)", sel)


def tab_to(page, sel, limit=80, key="Tab"):
    """Press Tab (or Shift+Tab) until focus is on sel; how many presses it took."""
    for n in range(1, limit + 1):
        page.keyboard.press(key)
        if focus_is(page, sel):
            return n
    raise AssertionError(f"{limit} presses of {key} never reached {sel}; focus is on {page.evaluate(ACTIVE)}")


def role(page):
    return page.evaluate("() => document.activeElement.getAttribute('role')")


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def wait_calls(page, server, n):
    for _ in range(100):
        if len(server.llm.calls) >= n:
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"the model was called {len(server.llm.calls)} times, not {n}")


def watch_body_focus(page):
    """From now on, note each time focus is left on the page body: after any focus move, and at every frame."""
    page.evaluate("""() => { window.__bodyFocus = [];
      const check = (why) => { if (document.activeElement === document.body) window.__bodyFocus.push(why); };
      document.addEventListener('focusout', () => queueMicrotask(() => setTimeout(() => check('focusout'), 0)), true);
      const tick = () => { check('frame'); window.__watch = requestAnimationFrame(tick); }; tick(); }""")


def body_focus(page):
    return page.evaluate("() => { cancelAnimationFrame(window.__watch); return window.__bodyFocus; }")


def two_sessions(server, session):
    other = server.store.create_session(str(server.repo), "main")
    server.store.update_session(other.id, title="older work")
    server.store.update_session(session.id, title="newer work")  # the newest: it opens first
    return other


# -- task 1: rows and links you can click are reachable (4.1, 4.2, 4.3) ------------------------------------------------


def test_a_search_hit_is_a_tab_stop_and_enter_opens_it_at_its_line(page, server, session):
    open_app(page)
    page.evaluate("setView('search')")  # (it focuses the search box)
    page.keyboard.type("return a")
    page.locator(".grep-hit").wait_for()
    tab_to(page, ".grep-file > .row")
    assert role(page) == "button"
    page.keyboard.press("Tab")
    assert focus_is(page, ".grep-hit[data-gline='2']") and role(page) == "button"
    page.keyboard.press("Enter")
    page.wait_for_function("() => state.active === 'file:agent/core.py'")
    page.locator("#editor .line-hl.flash").wait_for()  # at line 2
    assert focus_is(page, ".grep-hit[data-gline='2']")  # still where you were


def test_space_on_a_changed_file_opens_it(page, server, session):
    open_app(page)
    page.evaluate("setView('changes')")
    page.locator("#gitList [data-gitfile='Makefile']").wait_for()
    page.focus("#refreshGitBtn")
    tab_to(page, "#gitList [data-gitfile='Makefile']")
    page.keyboard.press(" ")
    page.wait_for_function("() => state.active === 'file:Makefile'")


def test_enter_on_a_session_opens_it_and_focus_stays_on_its_row_in_the_new_list(page, server, session):
    other = two_sessions(server, session)
    open_app(page)
    page.evaluate("setView('sessions')")
    page.focus("#sessFilter")
    tab_to(page, f".session[data-id='{other.id}']")
    watch_body_focus(page)
    page.keyboard.press("Enter")
    page.wait_for_function("(sid) => document.querySelector('#sessionList .session.on')?.dataset.id === sid",
                           arg=other.id)  # the list was drawn again, with the session it opened marked
    assert focus_is(page, f".session[data-id='{other.id}']"), page.evaluate(ACTIVE)
    assert body_focus(page) == []


def test_enter_on_a_sessions_delete_button_deletes_it_without_opening_it(page, server, session):
    other = two_sessions(server, session)
    open_app(page)
    page.evaluate("setView('sessions')")
    page.focus("#sessFilter")
    tab_to(page, f".session[data-id='{other.id}']")
    page.keyboard.press("Tab")  # its own Delete button, shown while the row has focus
    assert focus_is(page, f".session[data-id='{other.id}'] [data-del]")
    assert page.locator(f".session[data-id='{other.id}'] [data-del]").is_visible()
    asked = []
    page.once("dialog", lambda d: (asked.append(d.message), d.accept()))
    page.keyboard.press("Enter")
    page.wait_for_function("(sid) => !document.querySelector(`.session[data-id='${sid}']`)", arg=other.id)
    assert asked == ["Delete this session and its history?"]
    assert page.evaluate("() => state.sid") == session.id  # the row wasn't opened on the way
    page.wait_for_function("() => document.activeElement !== document.body")  # (the list's first row)
    assert focus_is(page, "#sessionList .session")


def test_a_path_in_a_reply_is_a_link_and_enter_opens_the_file(page, server, session):
    open_app(page)
    send(page, "hello")
    wait_idle(page)
    page.focus("#input")
    tab_to(page, "#transcript a.loc[data-path='agent/core.py']", key="Shift+Tab")
    assert role(page) == "link"
    page.keyboard.press("Enter")
    page.wait_for_function("() => state.active === 'file:agent/core.py'")


def test_enter_on_a_proposed_change_opens_it_in_review(page, server, session):
    p = server.store.add_proposal(session.id, "agent/core.py", "a - b", "a + b", "fix the sign")
    open_app(page)
    page.evaluate("setView('changes')")
    page.focus("#refreshGitBtn")
    tab_to(page, f"#proposalList [data-prop-open='{p.id}']")
    page.keyboard.press("Enter")
    page.wait_for_function("(id) => state.active === 'review'"
                           " && document.querySelector('.rv-item.on')?.dataset.rv == id", arg=p.id)


def test_in_review_enter_selects_a_row_and_focus_follows_the_selection(page, server, session):
    server.store.add_proposal(session.id, "agent/core.py", "a - b", "a + b", "fix the sign")
    server.store.add_proposal(session.id, "Makefile", "echo eval", "echo evaluate", "say more")
    open_app(page)
    page.evaluate("openReview()")
    page.locator(".rv-item").nth(1).wait_for()
    first, second = page.evaluate("() => [...document.querySelectorAll('.rv-item')].map((r) => r.dataset.rv)")
    page.focus("#rvApplyAll")
    tab_to(page, f".rv-item[data-rv='{second}']")
    watch_body_focus(page)
    page.keyboard.press("Enter")  # the list is drawn again, with this row selected
    page.locator(f".rv-item.on[data-rv='{second}']").wait_for()
    assert focus_is(page, f".rv-item[data-rv='{second}']"), page.evaluate(ACTIVE)
    page.keyboard.press("k")
    page.locator(f".rv-item.on[data-rv='{first}']").wait_for()
    assert focus_is(page, f".rv-item[data-rv='{first}']"), page.evaluate(ACTIVE)
    assert body_focus(page) == []


def test_j_and_k_keep_the_selected_change_in_view_in_a_short_stacked_list(page, server, session):
    for i in range(12):
        server.store.add_proposal(session.id, "agent/core.py", "a - b", f"a + b  # {i}", f"change {i}")
    page.set_viewport_size({"width": 1024, "height": 700})
    open_app(page)
    page.evaluate("openReview()")
    page.locator(".rv-item").nth(11).wait_for()
    page.evaluate("document.activeElement.blur()")
    for _ in range(11):
        page.keyboard.press("j")
        assert page.evaluate("""() => { const r = document.querySelector('.rv-item.on').getBoundingClientRect();
          const l = document.querySelector('.rv-list').getBoundingClientRect();
          return r.top >= l.top - 1 && r.bottom <= l.bottom + 1; }"""), "the selected change is out of view"


def test_the_welcome_links_and_the_context_meter_work_by_keyboard(page, server, session):
    open_app(page)
    page.focus("#chatTitleBtn")
    tab_to(page, "#wFind", key="Shift+Tab")  # (no tabs open: the welcome page)
    assert role(page) == "button"
    page.keyboard.press("Enter")
    page.locator("#palette").wait_for()
    page.keyboard.press("Escape")
    page.focus("#input")
    tab_to(page, "#sbContext")
    page.keyboard.press("Enter")
    page.locator("#dialog").wait_for()
    assert page.text_content("#dialogTitle") == "Compact conversation"


def test_a_spec_and_a_steering_doc_open_from_their_lists(page, server, session):
    specs = server.repo / ".codepilot/specs/demo"
    specs.mkdir(parents=True)
    for doc in ("requirements", "design", "tasks"):
        (specs / f"{doc}.md").write_text(f"# {doc}\n")
    (specs / "spec.json").write_text('{"kind": "feature", "approved": ""}')
    steering = server.repo / ".codepilot/steering"
    steering.mkdir(parents=True)
    (steering / "style.md").write_text("Use tabs.\n")
    open_app(page)
    page.evaluate("setView('specs')")
    page.locator("#specsView [data-spec-open='demo']").wait_for()
    page.focus("#refreshSpecsBtn")
    tab_to(page, "#specsView [data-spec-open='demo']")
    page.keyboard.press("Enter")
    page.wait_for_function("() => state.active === 'spec:demo'")
    page.evaluate("setView('steering')")
    page.locator("#steeringView .row.steer").first.wait_for()
    page.focus("#refreshSteeringBtn")
    tab_to(page, "#steeringView .row.steer")
    page.keyboard.press(" ")
    page.wait_for_function("() => (state.active || '').includes('style.md')")


# -- the audit (4.5) -------------------------------------------------------------------------------------------------

# Every visible element that looks clickable (a pointer cursor, or grab for a row you can drag) must be focusable
# itself or sit inside something focusable. A <label> around a switch or checkbox is fine: its control is inside it.
AUDIT = """(allowed) => {
  const FOCUSABLE = 'a[href], button, input, select, textarea, summary, [tabindex], [contenteditable]';
  const found = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.xterm') || !el.getClientRects().length) continue;
    const cs = getComputedStyle(el);
    if (!['pointer', 'grab'].includes(cs.cursor) || cs.visibility !== 'visible') continue;
    if (el.closest(FOCUSABLE) || el.closest('label')?.querySelector('input, select, textarea')) continue;
    if (allowed.some((s) => el.closest(s))) continue;
    const up = el.parentElement;
    // (reported once, as its row)
    if (up && ['pointer', 'grab'].includes(getComputedStyle(up).cursor) && !up.closest(FOCUSABLE)) continue;
    const data = [...el.attributes].filter((a) => a.name.startsWith('data-')).map((a) => `[${a.name}]`).join('');
    found.add(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${[...el.classList].map((c) => '.' + c).join('')}`
      + `${data} in #${up?.closest('[id]')?.id}`);
  }
  return [...found];
}"""

# Still unreachable, each until the task that makes it so; a task starts by taking its line out (task 2: the tree and
# the code view's line numbers; task 3: the tabs).
NOT_YET = ["#tree .row", "#gutter", "#editorTabs .tab"]


def audit(page, screen):
    # What was just drawn is decorated at the next frame (or the next key, whichever is first): look after one.
    page.evaluate("() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")
    found = page.evaluate(AUDIT, NOT_YET)
    assert not found, f"{screen}: clickable but not reachable by keyboard: {found}"


def test_nothing_you_can_click_is_out_of_reach_of_the_keyboard(page, server, session):
    server.store.add_proposal(session.id, "Makefile", "echo eval", "echo evaluate", "say more")
    (server.repo / ".codepilot/steering").mkdir(parents=True)
    (server.repo / ".codepilot/steering/style.md").write_text("Use tabs.\n")
    open_app(page)
    audit(page, "welcome")
    page.evaluate("openFile('agent/core.py')")
    page.locator("#gutter").wait_for()
    audit(page, "a file open")
    page.evaluate("setView('changes')")
    page.locator("#gitList .row").first.wait_for()
    audit(page, "Changes")
    page.evaluate("setView('search')")
    page.keyboard.type("return")
    page.locator(".grep-hit").first.wait_for()
    audit(page, "Search with hits")
    send(page, "fix it")
    wait_idle(page)
    send(page, "hello")
    wait_idle(page)
    page.locator("#transcript .tool, #transcript .card.prop").first.wait_for()
    audit(page, "a chat with steps and a change")
    page.evaluate("openReview()")
    page.locator(".rv-item").nth(1).wait_for()
    audit(page, "Review")
    page.evaluate("setView('sessions')")
    page.locator("#sessionList .session").first.wait_for()
    audit(page, "Sessions")
    page.evaluate("setView('steering')")
    page.locator("#steeringView .row.steer").first.wait_for()
    audit(page, "Steering")


# The ring on a focused row against what's behind it (the row's fill over the surface beneath), 3:1 or more: WCAG's
# minimum for something that isn't text. Translucent fills (a selected row's) are composited as the page draws them.
RING = """() => {
  const el = document.activeElement, cs = getComputedStyle(el);
  const rgba = (c) => { const v = c.match(/[\\d.]+/g).map(Number); return [v[0], v[1], v[2], v[3] ?? 1]; };
  let bg = [0, 0, 0, 0];
  for (let n = el; n && bg[3] < 1; n = n.parentElement) {
    const [r, g, b, a] = rgba(getComputedStyle(n).backgroundColor);  // under what's collected so far
    const k = a * (1 - bg[3]);
    bg = [bg[0] + r * k, bg[1] + g * k, bg[2] + b * k, bg[3] + k];
  }
  bg = bg.slice(0, 3).map((c) => c / (bg[3] || 1));
  const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const lum = ([r, g, b]) => 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  const [x, y] = [lum(rgba(cs.outlineColor)), lum(bg)].sort((p, q) => q - p);
  return { style: cs.outlineStyle, width: parseFloat(cs.outlineWidth), ratio: (x + 0.05) / (y + 0.05) };
}"""


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_a_focused_row_shows_a_ring_that_meets_contrast_selected_or_not(page, server, session, theme):
    other = two_sessions(server, session)
    open_app(page)
    page.evaluate(f"document.documentElement.dataset.theme = '{theme}'")
    page.evaluate("setView('sessions')")
    page.focus("#sessFilter")
    for row in (f".session.on[data-id='{session.id}']", f".session[data-id='{other.id}']"):
        tab_to(page, row)
        ring = page.evaluate(RING)
        assert ring["style"] == "solid" and ring["width"] >= 2 and ring["ratio"] >= 3, (row, ring)
