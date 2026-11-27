"""Tabs come back (spec restore-tabs): after a reload the folder's tabs, their order, the active one, each file's place
and the Explorer's open folders are back; unsaved edits too, and each folder keeps its own tabs."""

import base64
import json
import time

from test_files_ui import TOP_LINE, scroll_to_line
from uihelpers import click_editor, editor_open, editor_text, open_app, set_editor_text, wait_editor

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9aw"
                       "AAAABJRU5ErkJggg==")
TAB_IDS = "() => [...document.querySelectorAll('#editorTabs .tab')].map((t) => t.dataset.tab)"
ACTIVE = "() => document.querySelector('#editorTabs .tab.on')?.dataset.tab"


def tab_ids(page):
    return page.evaluate(TAB_IDS)


def wait_tabs(page, n):
    page.wait_for_function(f"() => document.querySelectorAll('#editorTabs .tab').length === {n}")


def reload(page, wait_tree=True):
    page.reload()
    page.wait_for_function("() => document.querySelector('#sbProvider')?.textContent.length > 0")
    if wait_tree:
        page.locator("#tree [data-file], #tree [data-dir]").first.wait_for()


def wait_saved(page):
    """Past the 300 ms debounce, so what the page shows is what's stored."""
    page.wait_for_timeout(400)


def demo_spec(server):
    folder = server.repo / ".codepilot/specs/demo"
    folder.mkdir(parents=True)
    (folder / "requirements.md").write_text("# R\n")
    (folder / "design.md").write_text("# D\n")
    (folder / "tasks.md").write_text("- [ ] 1. One\n")
    (folder / "spec.json").write_text('{"kind": "feature", "approved": "tasks"}')


def long_file(server, name="long.py", lines=300):
    (server.repo / name).write_text("".join(f"value_{i} = {i}\n" for i in range(1, lines + 1)))


# -- task 1: tabs, their place and the Explorer's open folders ------------------------------------------------------


def test_every_kind_of_tab_comes_back_in_order_with_the_same_one_active(page, server, session):
    long_file(server)
    (server.repo / "logo.png").write_bytes(PNG)
    (server.repo / "data.bin").write_bytes(b"\x00\x01\x02binary")
    demo_spec(server)
    server.store.add_proposal(session.id, "agent/core.py", "a - b", "a + b", "fix the sign")  # Review has a change
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.click("#tree [data-file='long.py']")
    page.click("#tree [data-file='logo.png']")
    page.click("#tree [data-file='data.bin']")
    for n, opener in enumerate(["openTrace('traces/run.jsonl')", "openSpec('demo')", "openReview()", "openGitDiff()"]):
        page.evaluate(opener)
        wait_tabs(page, 5 + n)  # one at a time, so the order is known (a spec waits for the spec list)
    page.locator("#editorTabs [data-tab='file:long.py']").click()
    before = tab_ids(page)
    assert before == ["file:agent/core.py", "file:long.py", "file:logo.png", "file:data.bin", "trace:traces/run.jsonl",
                      "spec:demo", "review", "gitdiff"]
    wait_saved(page)

    reload(page)
    wait_tabs(page, 8)
    assert tab_ids(page) == before
    assert page.evaluate(ACTIVE) == "file:long.py"
    page.locator("#editor code", has_text="value_300").wait_for()
    assert page.locator("#tree [data-file='agent/core.py']").count() == 1  # agent/ is still open (1.4)
    assert page.evaluate("() => state.tabs.map((t) => t.kind)") == [
        "file", "file", "image", "binary", "trace", "spec", "review", "gitdiff"]


def test_a_file_comes_back_at_its_line_with_its_selection(page, server, session):
    long_file(server)
    open_app(page)
    page.click("#tree [data-file='long.py']")
    page.locator("#editor code", has_text="value_300").wait_for()
    page.click("#gutter [data-ln='85']")
    page.click("#gutter [data-ln='90']", modifiers=["Shift"])
    scroll_to_line(page, "#edScroll", 80)
    wait_saved(page)

    reload(page)
    page.locator("#editor code", has_text="value_300").wait_for()
    assert abs(page.evaluate(TOP_LINE, "#edScroll") - 80) <= 1
    assert page.locator("#gutter .sel").count() == 6  # lines 85–90
    assert page.locator("#editor .line-hl.flash").count() == 0  # a place, not a jump: nothing flashes


def test_markdown_comes_back_in_preview_at_its_scroll_and_in_source_at_its_line(page, server, session):
    (server.repo / "GUIDE.md").write_text("# Guide\n\n" + "".join(f"Paragraph {i}.\n\n" for i in range(1, 200)))
    (server.repo / "NOTES.md").write_text("".join(f"line {i}\n" for i in range(1, 200)))
    open_app(page)
    page.click("#tree [data-file='NOTES.md']")  # Source by default
    page.locator("#editor code", has_text="line 199").wait_for()
    scroll_to_line(page, "#edScroll", 60)
    page.click("#tree [data-file='GUIDE.md']")
    page.locator("#editor [data-view-mode='preview']").click()
    page.locator("#docBody", has_text="Paragraph 199").wait_for()
    page.evaluate("() => { const el = document.querySelector('#edScroll'); el.scrollTop = 900; "
                  "el.dispatchEvent(new Event('scroll')); }")
    scrolled = page.evaluate("() => document.querySelector('#edScroll').scrollTop")
    assert scrolled > 500
    wait_saved(page)

    reload(page)
    page.locator("#docBody", has_text="Paragraph 199").wait_for()  # still Preview
    assert page.locator("#editor [data-view-mode='preview'].on").count() == 1
    assert abs(page.evaluate("() => document.querySelector('#edScroll').scrollTop") - scrolled) <= 2
    page.locator("#editorTabs [data-tab='file:NOTES.md']").click()
    page.locator("#editor code", has_text="line 199").wait_for()  # still Source
    assert abs(page.evaluate(TOP_LINE, "#edScroll") - 60) <= 1


def test_a_tab_whose_file_is_gone_is_left_out_quietly(page, server, session):
    (server.repo / "gone.py").write_text("x = 1\n")
    open_app(page)
    page.click("#tree [data-file='gone.py']")
    page.click("#tree [data-file='Makefile']")
    wait_tabs(page, 2)
    wait_saved(page)
    (server.repo / "gone.py").unlink()

    reload(page)
    wait_tabs(page, 1)
    page.wait_for_timeout(300)  # anything still to come would be here by now
    assert tab_ids(page) == ["file:Makefile"]
    assert page.locator(".toast").count() == 0  # no error (and the page fixture fails on a console error)


def test_a_closed_tab_stays_closed(page, server, session):
    open_app(page)
    page.click("#tree [data-file='Makefile']")
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    wait_tabs(page, 2)
    page.locator("#editorTabs [data-tab='file:Makefile']").hover()
    page.locator("#editorTabs [data-tab='file:Makefile'] [data-close]").click()
    wait_tabs(page, 1)
    page.click("#collapseTreeBtn")
    wait_saved(page)

    reload(page)
    wait_tabs(page, 1)
    assert tab_ids(page) == ["file:agent/core.py"]
    assert page.locator("#tree [data-file='agent/core.py']").count() == 0  # agent/ was closed too


def test_tabs_of_a_folder_not_opened_for_30_days_are_removed(page, server, session):
    now = time.time()
    old = {"v": 1, "at": now - 31 * 86400, "active": None, "expanded": [], "tabs": []}
    recent = {**old, "at": now - 29 * 86400}
    page.add_init_script(f"""if (!sessionStorage.getItem('planted')) {{ sessionStorage.setItem('planted', '1');
      localStorage.setItem('cp-tabs:/old/folder', {json.dumps(json.dumps(old))});
      localStorage.setItem('cp-tabs:/recent/folder', {json.dumps(json.dumps(recent))}); }}""")
    open_app(page)
    keys = page.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('cp-tabs:'))")
    assert "cp-tabs:/old/folder" not in keys
    assert "cp-tabs:/recent/folder" in keys


def test_only_the_20_most_recent_folders_are_kept(page, server, session):
    now = time.time()
    plant = {f"cp-tabs:/f{i}": json.dumps({"v": 1, "at": now - i * 60, "tabs": []}) for i in range(25)}
    page.add_init_script(f"""if (!sessionStorage.getItem('planted')) {{ sessionStorage.setItem('planted', '1');
      for (const [k, v] of Object.entries({json.dumps(plant)})) localStorage.setItem(k, v); }}""")
    open_app(page)
    keys = page.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('cp-tabs:/f'))")
    assert sorted(keys, key=lambda k: int(k.split("/f")[1])) == [f"cp-tabs:/f{i}" for i in range(20)]


# -- task 2: unsaved edits ---------------------------------------------------------------------------------------------

# Every toast the page shows, kept after it fades, so a test can count them.
COUNT_TOASTS = """window.__toasts = []; addEventListener('DOMContentLoaded', () => new MutationObserver((ms) => {
  for (const m of ms) for (const n of m.addedNodes) if (n.classList?.contains('toast')) window.__toasts.push(n.textContent);
}).observe(document.body, { childList: true, subtree: true }));"""


def edit_core(page, text="# mine\n", settle=True):
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.click("#fEdit")
    wait_editor(page)
    page.keyboard.type(text)  # at the top: the caret starts on the line you were reading
    page.wait_for_function("() => document.querySelector('.tab.on').classList.contains('dirty')")
    if settle:
        wait_saved(page)


def save(page):
    page.click("#fSave")


def test_an_unsaved_edit_comes_back_after_a_reload_and_saves(page, server, session):
    core = server.repo / "agent" / "core.py"
    open_app(page)
    edit_core(page)

    reload(page)
    wait_editor(page)
    assert editor_text(page) == "# mine\n" + core.read_text()
    assert page.locator("#editorTabs .tab.on.dirty").count() == 1
    assert page.locator("#edState").text_content() == "Unsaved changes"
    save(page)
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    assert core.read_text().startswith("# mine\ndef add")


def test_an_edit_to_a_file_changed_on_disk_is_kept_said_once_and_save_asks(page, server, session):
    core = server.repo / "agent" / "core.py"
    page.expected_errors.append("409 (Conflict)")
    page.add_init_script(COUNT_TOASTS)
    open_app(page)
    edit_core(page)
    core.write_text("theirs = 1\n")

    reload(page)
    wait_editor(page)
    assert editor_text(page).startswith("# mine\ndef add")  # your edit, not theirs
    page.wait_for_function("() => window.__toasts.some((t) => t.includes('changed on disk'))", timeout=5000)
    page.wait_for_timeout(2500)  # past the next look at the disk (every 2 s)
    assert len([t for t in page.evaluate("window.__toasts") if "changed on disk" in t]) == 1
    save(page)
    page.locator("#dialogTitle", has_text="changed on disk").wait_for()
    page.click("#dialogOk")  # Overwrite
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    assert core.read_text().startswith("# mine\ndef add")


def test_an_edit_to_a_deleted_file_comes_back_and_save_writes_the_file_again(page, server, session):
    core = server.repo / "agent" / "core.py"
    page.add_init_script(COUNT_TOASTS)
    open_app(page)
    edit_core(page)
    original = core.read_text()
    core.unlink()

    reload(page)
    wait_editor(page)
    assert editor_text(page) == "# mine\ndef add(a, b):\n    return a - b\n"
    assert page.locator("#editorTabs .tab.on.dirty").count() == 1
    page.wait_for_timeout(2500)
    gone = [t for t in page.evaluate("window.__toasts") if "core.py" in t]
    assert len(gone) == 1 and "deleted" in gone[0], gone
    save(page)
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    assert core.read_text() == "# mine\n" + original


def test_a_draft_too_large_to_store_asks_before_the_page_is_left(page, server, session):
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.type), d.accept()))
    open_app(page)
    page.click("#tree [data-file='Makefile']")
    page.click("#fEdit")
    set_editor_text(page, "x" * 1_200_000)
    click_editor(page)  # a real click: Chrome asks only on a page you've used
    page.wait_for_function("() => document.querySelector('.tab.on').classList.contains('dirty')")

    reload(page)
    assert dialogs == ["beforeunload"]
    wait_tabs(page, 1)  # the tab is back, without the edit it couldn't keep
    assert page.locator("#editorTabs .tab.dirty").count() == 0


def test_storage_that_is_full_asks_before_the_page_is_left(page, server, session):
    page.add_init_script("""const set = Storage.prototype.setItem; Storage.prototype.setItem = function (k, v) {
      if (k.startsWith('cp-tabs:')) throw new DOMException('full', 'QuotaExceededError'); return set.call(this, k, v); };""")
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.type), d.accept()))
    open_app(page)
    edit_core(page)
    click_editor(page)

    reload(page)
    assert dialogs == ["beforeunload"]


def test_a_stored_draft_leaves_without_asking(page, server, session):
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.type), d.accept()))
    open_app(page)
    edit_core(page)
    click_editor(page)

    reload(page)
    wait_editor(page)
    assert dialogs == []


def test_a_discarded_edit_stays_discarded(page, server, session):
    open_app(page)
    edit_core(page)
    page.click("#fDone")
    page.click("#dialogOk")  # Discard
    page.locator("#editor code", has_text="a - b").wait_for()
    wait_saved(page)

    reload(page)
    page.locator("#editor code", has_text="a - b").wait_for()
    assert not editor_open(page)
    assert page.locator("#editorTabs .tab.dirty").count() == 0


# -- task 3: each folder keeps its own tabs ----------------------------------------------------------------------------


def lib_session(server, tmp_path, session):
    lib = tmp_path / "lib"
    (lib / "pkg").mkdir(parents=True)
    (lib / "pkg" / "mod.py").write_text("LIB = 1\n")
    other = server.store.create_session(str(lib), "main")
    server.store.update_session(session.id, title="target work")  # the newest: it opens first
    return other


def switch(page, sid):
    page.click("#chatTitleBtn")
    page.locator(f"#sessPop .sess-opt[data-id='{sid}']").click()
    page.wait_for_function("(sid) => state.sid === sid && state.workspace", arg=sid)


def test_each_folder_keeps_its_own_tabs_and_drafts(page, server, session, tmp_path):
    other = lib_session(server, tmp_path, session)
    demo_spec(server)
    (server.repo / "logo.png").write_bytes(PNG)
    server.store.add_proposal(session.id, "agent/core.py", "a - b", "a + b", "fix the sign")
    open_app(page)
    page.click("#tree [data-file='Makefile']")
    page.click("#tree [data-file='logo.png']")
    page.evaluate("openSpec('demo')")
    wait_tabs(page, 3)
    page.evaluate("openReview()")
    edit_core(page, settle=False)  # and switch at once, before the edit's own save would run
    target_tabs = tab_ids(page)
    assert len(target_tabs) == 5

    switch(page, other.id)  # lib's tabs (none yet) replace these: images, specs and Review don't carry over
    page.locator("#tree [data-dir='pkg']").wait_for()
    wait_tabs(page, 0)
    page.click("#tree [data-dir='pkg']")
    page.click("#tree [data-file='pkg/mod.py']")
    wait_tabs(page, 1)
    wait_saved(page)

    switch(page, session.id)  # target's are back, the draft too
    wait_tabs(page, 5)
    assert tab_ids(page) == target_tabs
    assert page.evaluate(ACTIVE) == "file:agent/core.py"
    assert editor_text(page).startswith("# mine\n")
    assert page.locator("#editorTabs .tab.dirty").count() == 1

    switch(page, other.id)
    wait_tabs(page, 1)
    assert tab_ids(page) == ["file:pkg/mod.py"]
    # with pkg/ open. The tab and the tree are fetched separately, so the tree may still be on its way.
    page.locator("#tree [data-file='pkg/mod.py']").wait_for()


def test_sessions_on_one_folder_share_its_tabs(page, server, session):
    second = server.store.create_session(str(server.repo), "main")
    server.store.update_session(session.id, title="first")
    open_app(page)
    page.click("#tree [data-file='Makefile']")
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    wait_tabs(page, 2)

    switch(page, second.id)
    wait_tabs(page, 2)
    wait_saved(page)
    reload(page)  # the second session, on the same folder: the same tabs
    page.wait_for_function("(sid) => state.sid === sid", arg=second.id)
    wait_tabs(page, 2)
    assert tab_ids(page) == ["file:Makefile", "file:agent/core.py"]


def test_review_comes_back_only_for_a_session_with_changes(page, server, session):
    second = server.store.create_session(str(server.repo), "main")
    server.store.add_proposal(session.id, "agent/core.py", "a - b", "a + b", "fix the sign")
    server.store.update_session(session.id, title="first")
    open_app(page)
    page.click("#tree [data-file='Makefile']")
    page.evaluate("openReview()")
    wait_tabs(page, 2)
    wait_saved(page)

    reload(page)  # this session has a change to review
    wait_tabs(page, 2)
    switch(page, second.id)
    wait_saved(page)
    reload(page)  # this one has none: the Review tab would be empty
    page.wait_for_function("(sid) => state.sid === sid", arg=second.id)
    wait_tabs(page, 1)
    assert tab_ids(page) == ["file:Makefile"]
