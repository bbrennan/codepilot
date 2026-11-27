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


def test_a_messages_edit_retry_and_undo_are_reached_with_tab_and_shown_while_focused(page, server, session):
    open_app(page)
    send(page, "hello")
    wait_idle(page)
    actions = "#transcript .msg.user[data-mid] .msg-actions"
    assert page.evaluate(f"() => getComputedStyle(document.querySelector('{actions}')).opacity") == "0"
    page.focus("#chatTitleBtn")
    tab_to(page, f"{actions} [data-act='edit']")
    assert page.evaluate("() => document.activeElement.getAttribute('aria-label')").startswith("Edit")
    page.wait_for_function(f"() => getComputedStyle(document.querySelector('{actions}')).opacity === '1'")
    page.keyboard.press("Tab")
    assert focus_is(page, f"{actions} [data-act='retry']")
    assert page.evaluate("() => document.activeElement.getAttribute('aria-label')") == "Send again from here"
    page.keyboard.press("Enter")
    wait_calls(page, server, 2)  # sent again


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

# Still unreachable, each until the task that makes it so; a task starts by taking its line out (none now).
NOT_YET = []


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


# -- task 2: the file tree (1.1-1.5), and the code view's line numbers -------------------------------------------------

TREE_ROW = "#tree .row[data-file], #tree .row[data-dir]"


def into_tree(page):
    """Tab into the Explorer's tree from its own toolbar: one press."""
    page.evaluate("setView('explorer')")
    page.focus("#collapseTreeBtn")
    page.keyboard.press("Tab")
    assert page.evaluate("() => !!document.activeElement.closest('#tree')"), page.evaluate(ACTIVE)


def picked(page):
    return page.evaluate("() => { const r = document.activeElement.closest('#tree .row');"
                         " return r && (r.dataset.file || r.dataset.dir); }")


def test_the_tree_is_one_tab_stop_with_roles_and_levels(page, server, session):
    open_app(page)
    into_tree(page)
    assert page.evaluate("() => [document.querySelector('#tree').getAttribute('role'),"
                         " document.querySelector('#tree').getAttribute('aria-label')]") == ["tree", "Files"]
    assert page.evaluate(f"""() => [...document.querySelectorAll("{TREE_ROW}")].filter((r) => r.tabIndex === 0)
      .length""") == 1
    assert role(page) == "treeitem" and picked(page) == "agent"
    assert page.evaluate("() => [document.activeElement.getAttribute('aria-level'),"
                         " document.activeElement.getAttribute('aria-expanded')]") == ["1", "false"]
    page.keyboard.press("Tab")
    assert not page.evaluate("() => !!document.activeElement.closest('#tree')")  # out in one press
    page.keyboard.press("Shift+Tab")
    assert picked(page) == "agent"


def test_arrows_open_and_close_folders_and_enter_opens_a_file(page, server, session):
    open_app(page)
    into_tree(page)
    page.keyboard.press("ArrowRight")  # opens agent/
    page.locator("#tree [data-file='agent/core.py']").wait_for()
    assert picked(page) == "agent"
    assert page.evaluate("() => document.activeElement.getAttribute('aria-expanded')") == "true"
    page.keyboard.press("ArrowRight")  # into it
    assert picked(page) == "agent/core.py"
    assert page.evaluate("() => document.activeElement.getAttribute('aria-level')") == "2"
    page.keyboard.press("Enter")
    page.wait_for_function("() => state.active === 'file:agent/core.py'")
    assert picked(page) == "agent/core.py"  # focus stays in the tree
    page.keyboard.press("ArrowLeft")  # to its folder
    assert picked(page) == "agent"
    page.keyboard.press("ArrowLeft")  # closes it
    page.wait_for_function("() => !document.querySelector(\"#tree [data-file='agent/core.py']\")")
    assert picked(page) == "agent"
    page.keyboard.press("End")
    assert picked(page) == "Makefile"
    page.keyboard.press("Home")
    assert picked(page) == "agent"
    page.keyboard.press("ArrowDown")
    page.keyboard.press(" ")  # Space opens or closes a folder too
    page.locator("#tree [data-file='tests/test_core.py']").wait_for()
    assert picked(page) == "tests"
    page.keyboard.press("ArrowDown")
    assert picked(page) == "tests/test_core.py"
    page.keyboard.press("ArrowUp")
    assert picked(page) == "tests"


def test_typing_moves_to_the_next_row_starting_with_the_letters(page, server, session):
    (server.repo / "README.md").write_text("# Read me\n")
    (server.repo / "requirements.txt").write_text("")
    open_app(page)
    into_tree(page)
    page.keyboard.type("re")
    assert picked(page) == "README.md"
    page.wait_for_timeout(800)  # a pause starts a new search
    page.keyboard.type("r")
    assert picked(page) == "requirements.txt"


def test_f2_renames_and_delete_deletes_the_focused_row(page, server, session):
    open_app(page)
    into_tree(page)
    page.keyboard.press("End")
    assert picked(page) == "Makefile"
    page.keyboard.press("F2")
    page.locator("#dialog").wait_for()
    assert page.input_value("#dialogInput") == "Makefile"
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.querySelector('#dialog').hidden")
    page.reload()  # (focus coming back from a dialog is task 4's; here, start again)
    page.locator("#tree .row").first.wait_for()
    into_tree(page)
    page.keyboard.press("End")
    page.keyboard.press("Delete")
    page.locator("#dialog").wait_for()
    assert "Makefile" in page.text_content("#dialogTitle")


def test_mod_c_copies_the_focused_rows_path_and_only_there(page, server, session):
    open_app(page)
    into_tree(page)
    page.keyboard.press("End")
    page.keyboard.press("ControlOrMeta+c")
    page.wait_for_function("async () => (await navigator.clipboard.readText()) === 'Makefile'")
    page.evaluate("navigator.clipboard.writeText('before')")
    page.focus("#toggleChat")  # focus anywhere else, nothing selected
    page.keyboard.press("ControlOrMeta+c")
    page.wait_for_timeout(300)
    assert page.evaluate("navigator.clipboard.readText()") == "before"


def test_shift_f10_opens_the_focused_rows_menu(page, server, session):
    open_app(page)
    into_tree(page)
    page.keyboard.press("End")
    page.keyboard.press("Shift+F10")
    page.locator("#ctxMenu .mi", has_text="Rename…").wait_for()
    box = page.evaluate("() => { const m = document.querySelector('#ctxMenu').getBoundingClientRect(),"
                        " r = document.querySelector(\"#tree [data-file='Makefile']\").getBoundingClientRect();"
                        " return m.top >= r.top && m.left >= r.left && m.left < r.right; }")
    assert box, "the menu opens at the row"


def test_focus_stays_on_the_same_path_when_the_tree_redraws(page, server, session):
    open_app(page)
    into_tree(page)
    page.keyboard.press("End")
    watch_body_focus(page)
    (server.repo / "Aardvark.txt").write_text("first\n")  # appears above, from outside codepilot
    page.locator("#tree [data-file='Aardvark.txt']").wait_for()
    assert picked(page) == "Makefile", page.evaluate(ACTIVE)
    assert body_focus(page) == []



def test_in_review_letters_and_arrows_in_the_tree_belong_to_the_tree(page, server, session):
    server.store.add_proposal(session.id, "agent/core.py", "a - b", "a + b", "fix the sign")
    server.store.add_proposal(session.id, "Makefile", "echo eval", "echo evaluate", "say more")
    open_app(page)
    page.evaluate("openReview()")
    page.locator(".rv-item").nth(1).wait_for()
    sel = page.evaluate("() => document.querySelector('.rv-item.on').dataset.rv")
    into_tree(page)
    page.keyboard.type("a")
    page.keyboard.type("r")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    assert page.evaluate("() => [...state.proposals.values()].map((p) => p.status)") == ["pending", "pending"]
    assert page.evaluate("() => document.querySelector('.rv-item.on').dataset.rv") == sel
    page.evaluate("document.activeElement.blur()")  # on the page: Review's keys again
    page.keyboard.press("j")
    page.wait_for_function("(s) => document.querySelector('.rv-item.on').dataset.rv !== s", arg=sel)


def wait_sel(page, a, b):
    page.wait_for_function("([a, b]) => { const s = state.tabs.find((t) => t.id === state.active).sel;"
                           " return s?.a === a && s?.b === b; }", arg=[a, b])


def test_the_line_numbers_are_one_tab_stop_that_selects_lines(page, server, session):
    (server.repo / "long.py").write_text("".join(f"x_{i} = {i}\n" for i in range(1, 41)))
    open_app(page)
    page.evaluate("openFile('long.py')")
    page.locator("#gutter").wait_for()
    page.focus("#fReload")
    tab_to(page, "#gutter")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")  # line 3
    wait_sel(page, 3, 3)
    assert focus_is(page, "#gutter")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Shift+Enter")  # to line 5
    wait_sel(page, 3, 5)
    page.keyboard.press("End")
    assert page.evaluate("() => document.querySelector('#gutter').getAttribute('aria-activedescendant')") == "ln-40"
    page.keyboard.press(" ")
    wait_sel(page, 40, 40)
    assert page.evaluate("""() => { const r = document.querySelector('#ln-40').getBoundingClientRect(),
      s = document.querySelector('#edScroll').getBoundingClientRect();
      return r.top >= s.top && r.bottom <= s.bottom; }"""), "the line you're on is in view"


def test_the_bars_review_button_puts_you_in_the_review_where_a_applies(page, server, session):
    open_app(page)
    send(page, "fix two")
    page.locator("#rbReview").wait_for()
    wait_idle(page)
    page.focus("#input")
    tab_to(page, "#rbReview", key="Shift+Tab")
    page.keyboard.press("Enter")
    page.locator(".rv-item.on").wait_for()
    assert focus_is(page, ".rv-item.on"), page.evaluate(ACTIVE)
    page.keyboard.press("a")
    page.wait_for_function("() => [...state.proposals.values()].some((p) => p.status === 'applied')")


# -- task 3: tabs, the activity bar, menus and F6 (2.1-2.5, 3.1, 3.2) -----------------------------------------------


def three_tabs(page):
    for path in ("Makefile", "agent/core.py", "tests/test_core.py"):
        page.evaluate(f"openFile('{path}')")
        page.wait_for_function(f"() => state.active === 'file:{path}'")


def test_the_editor_tabs_are_one_tab_stop_that_arrows_move_through_and_delete_closes(page, server, session):
    open_app(page)
    three_tabs(page)
    into_tree(page)
    page.keyboard.press("Tab")  # from the tree to the editor's tabs: the one you're on
    assert focus_is(page, "#editorTabs [data-tab='file:tests/test_core.py']"), page.evaluate(ACTIVE)
    assert role(page) == "tab" and page.evaluate("() => document.activeElement.getAttribute('aria-selected')") == "true"
    assert page.evaluate("() => document.querySelector('#editorTabs').getAttribute('role')") == "tablist"
    assert page.evaluate("() => document.querySelector('#editor').getAttribute('role')") == "tabpanel"
    page.keyboard.press("ArrowLeft")  # moves and shows
    page.wait_for_function("() => state.active === 'file:agent/core.py'")
    assert focus_is(page, "#editorTabs [data-tab='file:agent/core.py']")
    page.keyboard.press("Home")
    page.wait_for_function("() => state.active === 'file:Makefile'")
    page.keyboard.press("End")
    page.wait_for_function("() => state.active === 'file:tests/test_core.py'")
    assert focus_is(page, "#editorTabs [data-tab='file:tests/test_core.py']")
    page.keyboard.press("Delete")
    page.wait_for_function("() => state.tabs.length === 2 && state.active === 'file:agent/core.py'")
    assert focus_is(page, "#editorTabs [data-tab='file:agent/core.py']"), page.evaluate(ACTIVE)
    page.keyboard.press("Tab")
    assert not page.evaluate("() => !!document.activeElement.closest('#editorTabs')")  # one stop
    names = page.evaluate("() => [...document.querySelectorAll('#editorTabs [data-close]')].map((b) =>"
                          " b.getAttribute('aria-label'))")
    assert names == ["Close Makefile", "Close core.py"]


def test_delete_on_a_tab_with_unsaved_edits_asks_first(page, server, session):
    open_app(page)
    three_tabs(page)
    page.evaluate("editFile('file:tests/test_core.py')")
    page.locator("#codeEdit").wait_for()
    page.focus("#codeEdit")
    page.keyboard.type("# mine\n")
    into_tree(page)
    page.keyboard.press("Tab")
    page.keyboard.press("Delete")
    page.locator("#dialog").wait_for()
    assert "Discard changes to test_core.py" in page.text_content("#dialogTitle")


def test_restored_tabs_do_not_move_focus(page, server, session):
    open_app(page)
    three_tabs(page)
    page.wait_for_timeout(400)  # (stored)
    page.reload()
    page.wait_for_function("() => document.querySelectorAll('#editorTabs .tab').length === 3")
    page.wait_for_timeout(200)
    assert page.evaluate(ACTIVE) == "body"


def test_the_panel_tabs_are_a_tab_list_too(page, server, session):
    open_app(page)
    page.keyboard.press("ControlOrMeta+j")  # the bottom panel
    page.locator("#activity").wait_for()
    page.focus("#clearActivity")
    page.keyboard.press("Shift+Tab")
    assert focus_is(page, ".panel-tabs [data-ptab='activity']") and role(page) == "tab"
    assert page.evaluate("() => document.querySelector('[data-ptab=activity]').closest('[role=tablist]')"
                         ".getAttribute('aria-label')") == "Panel"
    page.keyboard.press("ArrowRight")
    page.locator(".panel-body[data-ptab='output']").wait_for()
    assert focus_is(page, ".panel-tabs [data-ptab='output']")
    assert page.evaluate("() => [document.querySelector('[data-ptab=output]').getAttribute('aria-selected'),"
                         " document.querySelector('.panel-body[data-ptab=output]').getAttribute('role')]") == [
        "true", "tabpanel"]
    page.keyboard.press("Shift+Tab")
    assert not page.evaluate("() => !!document.activeElement.closest('[role=tablist]')")  # one stop


def test_the_activity_bar_says_which_view_is_shown_and_keeps_its_names_with_a_count(page, server, session):
    server.store.add_proposal(session.id, "agent/core.py", "a - b", "a + b", "fix the sign")
    open_app(page)
    pressed = "() => [...document.querySelectorAll('#activitybar button')].filter((b) =>" \
              " b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset.view)"
    assert page.evaluate(pressed) == ["explorer"]
    page.keyboard.press("ControlOrMeta+b")  # hidden: nothing is shown
    page.wait_for_function(f"() => ({pressed})().length === 0")
    page.keyboard.press("ControlOrMeta+b")
    page.wait_for_function(f"() => ({pressed})().join() === 'explorer'")
    page.evaluate("setView('search')")
    page.wait_for_function(f"() => ({pressed})().join() === 'search'")
    changes = page.locator("#activitybar [data-view=changes]")
    assert changes.get_attribute("aria-label") == "Changes, 1 waiting for review"
    assert page.get_attribute("#changesBadge", "aria-hidden") == "true"
    page.set_viewport_size({"width": 900, "height": 700})  # the sidebar steps aside for room (#126)
    page.wait_for_function("() => document.getElementById('ide').classList.contains('auto-no-sidebar')")
    page.wait_for_function(f"() => ({pressed})().length === 0")


def test_the_chat_title_says_it_switches_sessions(page, server, session):
    server.store.update_session(session.id, title="fix the sign")
    open_app(page)
    page.wait_for_function("() => document.querySelector('#chatTitleBtn').getAttribute('aria-label')"
                           " === 'Switch session: fix the sign'")


def test_a_menu_takes_focus_moves_with_arrows_and_gives_focus_back(page, server, session):
    open_app(page)
    page.focus("#fileMenuBtn")
    assert page.get_attribute("#fileMenuBtn", "aria-haspopup") == "menu"
    page.keyboard.press("Enter")
    page.locator("#ctxMenu").wait_for()
    assert page.get_attribute("#ctxMenu", "role") == "menu"
    assert focus_is(page, "#ctxMenu [role=menuitem]") and page.text_content("#ctxMenu :focus") == "New File…"
    assert page.get_attribute("#fileMenuBtn", "aria-expanded") == "true"
    page.keyboard.press("ArrowDown")
    assert page.text_content("#ctxMenu :focus") == "New Folder…"
    page.keyboard.press("End")
    assert page.text_content("#ctxMenu :focus") == "Go to File…" + page.evaluate("keyLabel('mod+p')")
    page.keyboard.press("ArrowDown")  # round to the top
    assert page.text_content("#ctxMenu :focus") == "New File…"
    page.keyboard.press("o")
    assert page.text_content("#ctxMenu :focus") == "Open Folder…"
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.querySelector('#ctxMenu').hidden")
    assert focus_is(page, "#fileMenuBtn")
    assert page.get_attribute("#fileMenuBtn", "aria-expanded") == "false"


def test_a_rows_menu_runs_an_item_and_focus_goes_back_to_the_row(page, server, session):
    open_app(page)
    into_tree(page)
    page.keyboard.press("End")
    page.keyboard.press("Shift+F10")
    page.locator("#ctxMenu").wait_for()
    assert page.text_content("#ctxMenu :focus") == "Open"
    page.keyboard.press("c")
    assert page.text_content("#ctxMenu :focus").startswith("Copy relative path")
    page.keyboard.press("Enter")
    page.wait_for_function("async () => (await navigator.clipboard.readText()) === 'Makefile'")
    assert page.evaluate("() => document.querySelector('#ctxMenu').hidden")
    assert picked(page) == "Makefile"


def test_f6_moves_between_the_panes_that_are_shown(page, server, session):
    open_app(page)
    page.evaluate("openFile('Makefile')")
    page.wait_for_function("() => state.active === 'file:Makefile'")
    page.focus("#input")
    page.keyboard.press("F6")  # chat → sidebar
    assert page.evaluate("() => !!document.activeElement.closest('#tree')"), page.evaluate(ACTIVE)
    page.keyboard.press("F6")  # → editor: the tab you're on
    assert focus_is(page, "#editorTabs [data-tab='file:Makefile']")
    page.keyboard.press("F6")  # the panel is closed: → chat
    assert focus_is(page, "#input")
    page.keyboard.press("Shift+F6")
    assert focus_is(page, "#editorTabs [data-tab='file:Makefile']")
    page.keyboard.press("ControlOrMeta+j")  # the panel open
    page.keyboard.press("F6")
    assert focus_is(page, ".panel-tabs [data-ptab].on")
    page.keyboard.press("ControlOrMeta+b")  # the sidebar hidden: skipped
    page.focus("#input")
    page.keyboard.press("F6")
    assert focus_is(page, "#editorTabs [data-tab='file:Makefile']")
    labels = page.evaluate("() => ['#activitybar', '#sidebar', '.center', '#panel', '#chat', '.statusbar']"
                           ".map((s) => document.querySelector(s).getAttribute('aria-label'))")
    assert labels == ["Views", "Sidebar", "Editor", "Panel", "Chat", "Status"]
