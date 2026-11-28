"""git where you work (spec git-changes): the Changes view's working tree and the Explorer's marks. Every repository
here is a temporary one made for the test (conftest.py's make_git_repo: an invented identity, no signing, no global
config), so nothing a test commits or discards can reach a real folder."""

import subprocess

import pytest
from gitrepos import make_git_repo
from test_keyboard_access_ui import audit
from uihelpers import open_app



@pytest.fixture(autouse=True)
def committed(git_repo):
    """The sample repo with one commit, before the server's page loads."""
    return git_repo


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


# The diff tab's section for a file is in view.
SHOWN = """(name) => { const f = [...document.querySelectorAll('#editor .f')].find((el) => el.textContent === name);
  if (!f) return false; const r = f.getBoundingClientRect(), s = f.closest('.ed-scroll').getBoundingClientRect();
  return r.top >= s.top && r.bottom <= s.bottom; }"""


def changes(page):
    page.evaluate("setView('changes')")
    page.locator("#gitList [data-gitfile]").first.wait_for()


def row(page, path):
    return page.locator(f"#gitList .git-row[data-gitrow='{path}']")


# -- task 1.2: a Changes list that reads plainly ----------------------------------------------------------------------


def test_each_change_has_a_letter_and_says_it_in_words(page, server, session):
    repo = server.repo
    (repo / "agent" / "core.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "new.py").write_text("x = 1\n")
    (repo / "Makefile").unlink()
    git(repo, "mv", "tests/test_core.py", "tests/test_add.py")
    open_app(page)
    changes(page)
    want = {"agent/core.py": ("M", "Modified"), "new.py": ("U", "Untracked"), "Makefile": ("D", "Deleted"),
            "tests/test_add.py": ("R", "Renamed")}
    for path, (letter, word) in want.items():
        mark = row(page, path).locator(".gmark")
        assert mark.inner_text() == letter and mark.get_attribute("title") == word
    assert "Renamed from tests/test_core.py" in row(page, "tests/test_add.py").locator("button.gname").get_attribute("title")
    assert page.locator("#gitList .git-row").count() == 4  # no "??", nothing twice
    assert row(page, "new.py").get_by_role("button", name="new.py, untracked", exact=True).count() == 1  # (as read)
    audit(page, "Changes with git rows")


def test_a_name_with_spaces_opens_its_own_file(page, server, session):
    (server.repo / "notes with spaces.txt").write_text("the real one\n")
    open_app(page)
    changes(page)
    row(page, "notes with spaces.txt").locator("button.gname").click()
    page.locator("#editor code", has_text="the real one").wait_for()
    assert page.evaluate("state.active") == "file:notes with spaces.txt"


def test_a_name_with_spaces_opens_by_keyboard_too(page, server, session):
    (server.repo / "notes with spaces.txt").write_text("the real one\n")
    open_app(page)
    changes(page)
    row(page, "notes with spaces.txt").locator("button.gname").focus()
    page.keyboard.press("Enter")
    page.locator("#editor code", has_text="the real one").wait_for()


@pytest.mark.parametrize("how", ["deleted on disk", "git rm"])
def test_a_deleted_file_opens_what_was_deleted_as_a_diff(page, server, session, how):
    if how == "git rm":
        git(server.repo, "rm", "-q", "Makefile")
    else:
        (server.repo / "Makefile").unlink()
    (server.repo / "agent" / "core.py").write_text("def add(a, b):\n    return a + b\n")  # (another file's diff above)
    open_app(page)
    changes(page)
    row(page, "Makefile").locator("button.gname").click()
    page.locator("#editorTabs [data-tab='gitdiff']").wait_for()
    head = page.locator("#editor .f", has_text="Makefile")
    head.wait_for()
    page.locator("#editor .dl", has_text="eval-bedrock:").wait_for()
    page.wait_for_function(SHOWN, arg="Makefile")  # scrolled to it
    page.reload()  # tabstate.js reopens the diff tab
    page.locator("#editorTabs [data-tab='gitdiff']").wait_for()
    page.locator("#editor .f", has_text="Makefile").wait_for()


def test_a_clean_working_tree_says_so(page, server, session):
    open_app(page)
    page.evaluate("setView('changes')")
    page.locator("#gitList", has_text="Clean working tree.").wait_for()
    assert page.locator("#gitList .git-row").count() == 0


def test_an_added_folders_changes_read_the_same_way(page, server, session, tmp_path):
    api = make_git_repo(_api_folder(tmp_path))
    (api / "my file é.py").write_text("y = 2\n")
    (api / "README.md").write_text("changed\n")
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    changes(page)
    full = str(api.resolve())
    assert row(page, f"{full}/README.md").locator(".gmark").get_attribute("title") == "Modified"
    row(page, f"{full}/my file é.py").locator("button.gname").click()
    page.locator("#editor code", has_text="y = 2").wait_for()


def _api_folder(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    (api / "README.md").write_text("api\n")
    return api


# -- task 1.3: marks in the Explorer ----------------------------------------------------------------------------------


# Counts the disk checks answered and the git requests in flight, for settle().
NET = """(() => { window.__net = { stat: 0, git: 0 }; const f = window.fetch;
  window.fetch = (url, ...rest) => { const u = String(url), p = f(url, ...rest);
    if (u.endsWith('/stat')) p.finally(() => window.__net.stat++);
    if (u.endsWith('/git')) { window.__net.git++; p.finally(() => window.__net.git--); }
    return p; }; })()"""


def settle(page):
    """Past the first disk checks and any git reload they started: a disk check runs every 2 s and the reload it asks
    for waits 500 ms, so after two checks one is done. A test then sees only what it does itself."""
    page.wait_for_function("() => window.__net.stat >= 2 && window.__net.git === 0")


def open_settled(page):
    page.add_init_script(NET)
    open_app(page)
    settle(page)


def tree_row(page, path):
    return page.locator(f"#tree .row[data-file='{path}'], #tree .row[data-dir='{path}']")


def wait_mark(page, path, letter):
    """The row's mark becomes letter ("" for none, "●" for a folder's dot)."""
    page.wait_for_function("""([p, letter]) => { const r = document.querySelector(
      `#tree .row[data-file="${CSS.escape(p)}"], #tree .row[data-dir="${CSS.escape(p)}"]`);
      return r && (r.querySelector('.gmark')?.textContent || '') === letter; }""", arg=[path, letter])


def test_changed_files_have_a_letter_and_their_folders_a_dot(page, server, session):
    (server.repo / "agent" / "core.py").write_text("def add(a, b):\n    return a + b\n")
    (server.repo / "tests" / "test_more.py").write_text("x = 1\n")
    open_app(page)
    wait_mark(page, "agent", "●")
    wait_mark(page, "tests", "●")
    wait_mark(page, "traces", "")  # untouched
    assert tree_row(page, "agent").get_attribute("aria-label") == "agent, contains changes"
    page.click("#tree [data-dir='agent']")
    wait_mark(page, "agent/core.py", "M")
    page.click("#tree [data-dir='tests']")
    wait_mark(page, "tests/test_more.py", "U")
    wait_mark(page, "tests/test_core.py", "")
    core = tree_row(page, "agent/core.py")
    assert core.get_attribute("data-git") == "modified" and core.locator(".gmark").get_attribute("title") == "Modified"
    # Read as one name ("core.py, modified"); the letter alone is hidden from a screen reader.
    assert page.get_by_role("treeitem", name="core.py, modified", exact=True).count() == 1
    assert page.get_by_role("treeitem", name="test_more.py, untracked", exact=True).count() == 1
    assert core.locator(".gmark").get_attribute("aria-hidden") == "true"


def test_the_marks_leave_the_trees_one_tab_stop_and_its_keys_alone(page, server, session):
    (server.repo / "agent" / "core.py").write_text("changed\n")
    open_app(page)
    page.click("#tree [data-dir='agent']")
    wait_mark(page, "agent/core.py", "M")
    stops = "() => [...document.querySelectorAll('#tree [tabindex=\"0\"]')].map((e) => e.dataset.file ?? e.dataset.dir)"
    assert page.evaluate(stops) == ["agent"]  # one roving stop, on the picked row; no mark is a stop
    assert page.locator("#tree .gmark[tabindex], #tree .gmark button").count() == 0
    tree_row(page, "agent").focus()
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.dataset.file") == "agent/core.py"
    page.keyboard.press("c")  # typing finds a row by its name, not by its mark
    page.keyboard.press("o")
    assert page.evaluate("document.activeElement.dataset.file") == "agent/core.py"
    audit(page, "the Explorer with marks")


def test_a_saved_file_gets_its_mark(page, server, session):
    from uihelpers import set_editor_text, wait_editor
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.locator("#fEdit").click()
    wait_editor(page)
    wait_mark(page, "agent/core.py", "")
    set_editor_text(page, "def add(a, b):\n    return a + b\n")
    page.keyboard.press("ControlOrMeta+s")
    wait_mark(page, "agent/core.py", "M")
    wait_mark(page, "agent", "●")


def test_an_applied_change_gets_its_mark_and_loses_it_on_undo(page, server, session):
    from test_ui import send, wait_idle
    open_app(page)
    page.click("#tree [data-dir='agent']")
    wait_mark(page, "agent/core.py", "")
    send(page, "fix the add bug")  # (the scripted model proposes a change to agent/core.py)
    card = page.locator(".card[data-prop]")
    card.wait_for()
    wait_idle(page)
    card.locator("[data-apply]").click()
    wait_mark(page, "agent/core.py", "M")
    card.locator("[data-revert]").click()
    wait_mark(page, "agent/core.py", "")


def test_a_commit_made_in_the_terminal_clears_the_marks_at_the_next_disk_check(page, server, session):
    """No working file changes in a commit: the disk check watches the index and the branch HEAD names. It runs every
    2 s; the test runs it at once rather than waiting for the interval."""
    (server.repo / "agent" / "core.py").write_text("changed\n")
    open_settled(page)
    wait_mark(page, "agent", "●")
    git(server.repo, "commit", "-qam", "in the terminal")
    page.evaluate("checkDisk()")
    wait_mark(page, "agent", "")
    git(server.repo, "reset", "-q", "HEAD~1")  # (and a reset brings it back)
    page.evaluate("checkDisk()")
    wait_mark(page, "agent", "●")


def test_a_changed_open_file_updates_the_marks(page, server, session):
    """An open file that changes on disk (an edit in place, which no folder's stamp shows) reloads the marks too."""
    open_settled(page)
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.locator("#editor code", has_text="a - b").wait_for()
    settle(page)  # (the folder just opened is a new one to check)
    with open(server.repo / "agent" / "core.py", "a") as f:
        f.write("# more\n")
    page.evaluate("checkDisk()")
    wait_mark(page, "agent/core.py", "M")


def test_an_added_folder_shows_its_own_repositorys_marks(page, server, session, tmp_path):
    api = make_git_repo(_api_folder(tmp_path))
    (api / "README.md").write_text("changed\n")
    (server.repo / "Makefile").write_text("changed\n")
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    full = str(api.resolve())
    wait_mark(page, f"{full}/README.md", "M")
    wait_mark(page, "Makefile", "M")
    roots = page.locator("#tree .row.root")
    assert roots.nth(1).locator(".gmark").text_content() == "●"  # the folder itself holds changes


@pytest.mark.parametrize("side", [180, 200])
def test_marks_fit_their_rows_in_a_narrow_sidebar(page, server, session, side):
    name = "a_file_with_a_long_name_that_will_not_fit_in_the_sidebar.py"
    (server.repo / "agent" / name).write_text("x\n")
    page.set_viewport_size({"width": 1024, "height": 700})
    page.add_init_script(f"localStorage.setItem('cp--sidebar-w', '{side}px')")
    open_app(page)
    page.click("#tree [data-dir='agent']")
    wait_mark(page, f"agent/{name}", "U")
    fits = """(sel) => { const row = document.querySelector(sel), r = row.getBoundingClientRect(),
      t = document.querySelector('#tree').getBoundingClientRect(), m = row.querySelector('.gmark').getBoundingClientRect();
      return { inTree: r.left >= t.left - 0.5 && r.right <= t.right + 0.5, inRow: m.left >= r.left && m.right <= r.right,
               oneLine: m.height <= r.height && r.height < 30, width: Math.round(t.width) }; }"""
    got = page.evaluate(fits, f"#tree .row[data-file='agent/{name}']")
    assert got == {"inTree": True, "inRow": True, "oneLine": True, "width": got["width"]} and got["width"] <= side


# Each of a Changes row's parts inside the row, the row inside the list, and all on one line.
ROW_FITS = """(sel) => { const row = document.querySelector(sel), r = row.getBoundingClientRect(),
  list = document.querySelector('#gitList').getBoundingClientRect();
  const parts = [...row.querySelectorAll('.gmark, .gname, input, button')].map((e) => e.getBoundingClientRect());
  return { inList: r.left >= list.left - 0.5 && r.right <= list.right + 0.5,
           partsIn: parts.every((p) => p.left >= r.left - 0.5 && p.right <= r.right + 0.5),
           oneLine: r.height < 30, side: Math.round(document.querySelector('.sidebar').getBoundingClientRect().width) }; }"""


@pytest.mark.parametrize("side", [180, 200])
def test_changes_rows_fit_a_narrow_sidebar(page, server, session, side):
    name = "a_file_with_a_long_name_that_will_not_fit_in_the_sidebar.py"
    (server.repo / "agent" / name).write_text("x\n")
    page.set_viewport_size({"width": 1024, "height": 700})
    page.add_init_script(f"localStorage.setItem('cp--sidebar-w', '{side}px')")
    open_app(page)
    changes(page)
    got = page.evaluate(ROW_FITS, f"#gitList .git-row[data-gitrow='agent/{name}']")
    assert got == {"inList": True, "partsIn": True, "oneLine": True, "side": got["side"]} and 180 <= got["side"] <= side


# -- task 2.2: tick boxes, the message box and Commit -----------------------------------------------------------------


def box(page, folder=""):
    """A repository's commit box: the main folder's, or an added folder's by its full path."""
    return page.locator(f"#gitList .git-commit[data-groot='{folder}']")


def tick(page, path):
    return page.locator(f"#gitList input[data-gtick='{path}']")


def why(page, folder=""):
    return box(page, folder).locator(".git-why").inner_text()


def changed(server, *names):
    for name in names:
        path = server.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name} changed\n")


def test_every_file_is_ticked_and_the_list_counts_them(page, server, session):
    changed(server, "Makefile", "agent/core.py", "new.py", "docs/a.md")
    open_app(page)
    changes(page)
    count = page.locator("#gitList .git-count").first
    assert count.inner_text() == "4 of 4" and all(t.is_checked() for t in page.locator("#gitList .gtick").all())
    tick(page, "new.py").uncheck()
    assert count.inner_text() == "3 of 4"
    tick_all = page.locator("#gitList .gtick-all").first
    assert tick_all.evaluate("(b) => b.indeterminate") and not tick_all.is_checked()
    tick_all.check()
    assert count.inner_text() == "4 of 4"
    tick_all.uncheck()
    assert count.inner_text() == "0 of 4"
    assert tick(page, "new.py").get_attribute("aria-label") == "Commit new.py"
    page.evaluate("loadGit()")  # a redraw keeps the ticks
    page.wait_for_function("() => document.querySelector('#gitList .git-count').textContent === '0 of 4'")


def test_commit_the_ticked_files_with_a_message(page, server, session):
    changed(server, "Makefile", "agent/core.py")
    open_app(page)
    changes(page)
    tick(page, "agent/core.py").uncheck()
    box(page).locator("textarea").fill("Say more in the eval")
    box(page).locator("button.gcommit").click()
    toast = page.locator(".toast", has_text="Committed")
    toast.wait_for()
    hash_ = git(server.repo, "rev-parse", "--short", "HEAD").strip()
    assert toast.inner_text() == f"Committed {hash_}: Say more in the eval"
    assert git(server.repo, "log", "-1", "--format=%s") == "Say more in the eval\n"
    assert git(server.repo, "show", "--name-only", "--format=", "HEAD").split() == ["Makefile"]
    page.wait_for_function("() => !document.querySelector(\"#gitList [data-gitrow='Makefile']\")")
    assert page.locator("#gitList .git-row").count() == 1 and row(page, "agent/core.py").count() == 1
    assert box(page).locator("textarea").input_value() == ""  # cleared
    assert page.evaluate("document.activeElement.matches('#gitList .git-commit textarea')")  # where you were
    page.evaluate("setView('explorer')")
    wait_mark(page, "Makefile", "")  # and the Explorer follows


def test_commit_says_why_it_is_unavailable(page, server, session):
    from test_ui import send
    changed(server, "Makefile")
    open_app(page)
    changes(page)
    button = box(page).locator("button.gcommit")
    assert button.is_disabled() and why(page) == "Write a message to commit."
    assert button.get_attribute("aria-describedby") == box(page).locator(".git-why").get_attribute("id")
    box(page).locator("textarea").fill("   ")
    assert button.is_disabled() and why(page) == "Write a message to commit."
    box(page).locator("textarea").fill("Ready")
    assert button.is_enabled() and why(page) == "" and button.inner_text() == "Commit 1"
    tick(page, "Makefile").uncheck()
    assert button.is_disabled() and why(page) == "Tick at least one file to commit."
    tick(page, "Makefile").check()
    send(page, "run ls")  # a turn that waits for your approval: the session is working
    page.locator("#reviewBar .rb-approval").wait_for()
    page.wait_for_function("() => document.querySelector('#gitList .git-commit .git-why').textContent"
                           " === 'codepilot is working: commit when the turn is done.'")
    assert button.is_disabled()


def test_a_refused_commit_shows_gits_words_and_changes_nothing(page, server, session):
    hook = server.repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'lint: 2 problems in Makefile' >&2\nexit 1\n")
    hook.chmod(0o755)
    changed(server, "Makefile")
    page.expected_errors.append("409 (Conflict)")
    open_app(page)
    changes(page)
    box(page).locator("textarea").fill("Will be refused")
    box(page).locator("button.gcommit").click()
    banner = box(page).locator(".banner.error")
    banner.wait_for()
    assert "lint: 2 problems in Makefile" in banner.inner_text() and banner.get_attribute("role") == "alert"
    assert git(server.repo, "status", "--porcelain") == " M Makefile\n"
    assert box(page).locator("textarea").input_value() == "Will be refused"  # kept, to try again


def test_cmd_enter_in_the_message_box_commits(page, server, session):
    changed(server, "Makefile")
    open_app(page)
    changes(page)
    box(page).locator("textarea").fill("By keyboard")
    box(page).locator("textarea").press("ControlOrMeta+Enter")
    page.locator(".toast", has_text="Committed").wait_for()
    assert git(server.repo, "log", "-1", "--format=%s") == "By keyboard\n"


def test_cmd_enter_in_the_message_box_never_approves_a_waiting_command(page, server, session):
    from test_ui import send, wait_idle
    changed(server, "Makefile")
    open_app(page)
    changes(page)
    send(page, "run ls")
    page.locator("#reviewBar .rb-approval").wait_for()
    box(page).locator("textarea").fill("Not now")
    box(page).locator("textarea").press("ControlOrMeta+Enter")
    assert page.evaluate("!!state.approval") and page.locator("#reviewBar .rb-approval").is_visible()
    assert git(server.repo, "log", "-1", "--format=%s") == "start\n"  # and nothing committed either
    assert box(page).locator("textarea").input_value() == "Not now"
    assert box(page).locator("button.gcommit").is_disabled() and "working" in why(page)
    page.click("#rbApprove")  # approved from its own button: the turn finishes, and Commit is there again
    wait_idle(page)
    page.wait_for_function("() => !document.querySelector('#gitList .gcommit').disabled")
    box(page).locator("textarea").press("ControlOrMeta+Enter")
    page.locator(".toast", has_text="Committed").wait_for()
    assert git(server.repo, "log", "-1", "--format=%s") == "Not now\n"


def test_an_added_folder_commits_to_its_own_repository(page, server, session, tmp_path):
    api = make_git_repo(_api_folder(tmp_path))
    full = str(api.resolve())
    (api / "README.md").write_text("changed\n")
    changed(server, "Makefile")
    server.store.update_session(session.id, folders=[full])
    open_app(page)
    changes(page)
    assert box(page, full).locator("textarea").get_attribute("aria-label") == "Commit message for api"
    box(page, full).locator("textarea").fill("In api")
    box(page, full).locator("button.gcommit").click()
    page.locator(".toast", has_text="Committed").wait_for()
    assert git(api, "log", "-1", "--format=%s") == "In api\n"
    assert git(server.repo, "log", "-1", "--format=%s") == "start\n"
    assert git(server.repo, "status", "--porcelain") == " M Makefile\n"


def test_focus_stays_on_its_control_when_the_list_redraws(page, server, session):
    changed(server, "Makefile", "agent/core.py", "new.py")
    open_app(page)
    changes(page)
    for target in ("input[data-gtick='agent/core.py']", "button[data-gitfile='agent/core.py']",
                   ".git-commit[data-groot=''] textarea"):
        page.locator(f"#gitList {target}").focus()
        page.evaluate("loadGit()")
        page.wait_for_function("(sel) => document.activeElement === document.querySelector(sel)",
                               arg=f"#gitList {target}")
    box(page).locator("textarea").fill("abc")
    box(page).locator("textarea").evaluate("(t) => t.setSelectionRange(1, 2)")
    page.evaluate("loadGit()")
    assert box(page).locator("textarea").evaluate("(t) => [t.value, t.selectionStart, t.selectionEnd]") == ["abc", 1, 2]
    # A committed row is gone: focus goes to the same control of the row that took its place.
    tick(page, "agent/core.py").focus()
    git(server.repo, "add", "agent/core.py")
    git(server.repo, "commit", "-qm", "elsewhere", "--", "agent/core.py")
    page.evaluate("loadGit()")
    page.wait_for_function("() => document.activeElement?.matches?.('#gitList input.gtick')")
    assert page.evaluate("document.activeElement.dataset.gtick") in ("Makefile", "new.py")
    audit(page, "Changes with tick boxes and a commit box")


@pytest.mark.parametrize("side", [180, 200])
def test_the_count_and_the_commit_box_fit_a_narrow_sidebar(page, server, session, side):
    changed(server, "Makefile", "agent/core.py", "a_file_with_a_long_name_that_will_not_fit_in_the_sidebar.py")
    page.set_viewport_size({"width": 1024, "height": 700})
    page.add_init_script(f"localStorage.setItem('cp--sidebar-w', '{side}px')")
    open_app(page)
    changes(page)
    box(page).locator("textarea").fill("x")
    fits = """() => { const list = document.querySelector('#gitList').getBoundingClientRect();
      const inside = (sel) => [...document.querySelectorAll(sel)].every((el) => { const r = el.getBoundingClientRect();
        return r.width > 0 && r.left >= list.left - 0.5 && r.right <= list.right + 0.5; });
      const head = document.querySelector('#gitList .git-head').getBoundingClientRect();
      return { head: inside('#gitList .git-head, #gitList .git-head > *'), oneLine: head.height < 30,
               box: inside('#gitList .git-commit, #gitList .git-commit textarea, #gitList .git-commit button'),
               rows: inside('#gitList .git-row, #gitList .git-row > *') }; }"""
    assert page.evaluate(fits) == {"head": True, "oneLine": True, "box": True, "rows": True}


def test_a_late_answer_for_a_session_you_left_is_not_drawn(page, server, session, tmp_path):
    """A git answer that arrives after you've opened another session belongs to the one you left: drawn, it showed the
    old folder's files under the new one (or threw, while the page had no folder to name it by)."""
    changed(server, "Makefile")
    other = make_git_repo(_api_folder(tmp_path))
    (other / "README.md").write_text("changed\n")
    held = []
    open_app(page)
    changes(page)
    row(page, "Makefile").wait_for()  # the first session's
    second = server.store.create_session(str(other), "main")  # (made now: the page opens the newest session)
    page.route("**/git", lambda route: held.append(route) if not held else route.continue_())
    with page.expect_request("**/git"):
        page.evaluate("() => { window.__late = loadGit(); }")  # (not awaited here: its answer is held)
    page.evaluate(f"openSession('{second.id}')")
    row(page, "README.md").wait_for()  # the second session's own answer, drawn
    held[0].continue_()  # the first session's, late
    page.evaluate("() => window.__late")  # that loadGit has finished: whatever it would draw is drawn
    assert row(page, "Makefile").count() == 0 and row(page, "README.md").count() == 1


# -- task 3.2: Discard in the list ------------------------------------------------------------------------------------


def discard_button(page, path):
    return page.locator(f"#gitList button[data-gdiscard='{path}']")


def ask_discard(page, path):
    """Press Discard and wait for its question: (title, hint)."""
    discard_button(page, path).click()
    page.locator("#dialog").wait_for()
    return page.locator("#dialogTitle").inner_text(), page.locator("#dialogHint").inner_text()


def toast_text(toast):
    return toast.evaluate("(t) => t.firstChild.textContent")


@pytest.mark.parametrize("what", ["modified", "untracked", "deleted"])
def test_discard_asks_first_naming_the_file_and_what_is_lost(page, server, session, what):
    path = {"modified": "agent/core.py", "untracked": "new.py", "deleted": "Makefile"}[what]
    if what == "deleted":
        (server.repo / path).unlink()
    else:
        changed(server, path)
    open_app(page)
    changes(page)
    assert discard_button(page, path).get_attribute("aria-label") == f"Discard changes to {path}"
    title, hint = ask_discard(page, path)
    assert title == f"Discard changes to {path}?"
    assert hint == {
        "modified": f"{path} goes back to the last commit. Your changes move to codepilot's trash; Undo puts them back.",
        "untracked": f"{path} isn't in the last commit, so it moves to codepilot's trash; Undo puts it back.",
        "deleted": f"{path} comes back as it was in the last commit.",
    }[what]
    page.click("#dialogCancel")  # and nothing happens
    assert git(server.repo, "status", "--porcelain").strip().endswith(path)


def test_discard_then_undo(page, server, session):
    changed(server, "agent/core.py", "Makefile")
    open_app(page)
    changes(page)
    ask_discard(page, "agent/core.py")
    page.click("#dialogOk")
    toast = page.locator(".toast", has_text="Discarded")
    toast.wait_for()
    assert toast_text(toast) == "Discarded changes to agent/core.py"
    assert (server.repo / "agent" / "core.py").read_text() == "def add(a, b):\n    return a - b\n"
    page.wait_for_function("() => !document.querySelector(\"#gitList [data-gitrow='agent/core.py']\")")
    toast.locator("button", has_text="Undo").click()
    page.locator(".toast", has_text="Put back agent/core.py").wait_for()
    assert (server.repo / "agent" / "core.py").read_text() == "agent/core.py changed\n"
    row(page, "agent/core.py").wait_for()


def test_undo_says_so_when_the_file_has_changed_since(page, server, session):
    changed(server, "new.py")
    page.expected_errors.append("409 (Conflict)")
    open_app(page)
    changes(page)
    ask_discard(page, "new.py")
    page.click("#dialogOk")
    toast = page.locator(".toast", has_text="Discarded")
    toast.wait_for()
    (server.repo / "new.py").write_text("made again\n")
    toast.locator("button", has_text="Undo").click()
    page.locator(".toast.err", has_text="changed since").wait_for()
    assert (server.repo / "new.py").read_text() == "made again\n"


def test_the_open_tab_shows_the_file_as_it_now_is(page, server, session):
    changed(server, "agent/core.py")
    open_app(page)
    page.evaluate("openFile('agent/core.py')")
    page.locator("#editor code", has_text="agent/core.py changed").wait_for()
    changes(page)
    ask_discard(page, "agent/core.py")
    page.click("#dialogOk")
    page.locator("#editor code", has_text="a - b").wait_for()  # the last commit's, in the tab that was open


def test_unsaved_edits_are_named_in_the_question_and_gone_after(page, server, session):
    """The editor (#134) with a draft stored for restore (#125): after the discard the editor shows the file as it now
    is, the draft is forgotten, and a reload doesn't bring it back."""
    from uihelpers import editor_text, set_editor_text, wait_editor
    changed(server, "agent/core.py")
    open_app(page)
    page.evaluate("openFile('agent/core.py')")
    page.locator("#fEdit").click()
    wait_editor(page)
    set_editor_text(page, "my unsaved draft\n")
    page.wait_for_function("() => Object.values(localStorage).some((v) => v.includes('my unsaved draft'))")
    changes(page)
    title, hint = ask_discard(page, "agent/core.py")
    assert hint.endswith(" Your unsaved edits in the open tab are lost too.")
    page.click("#dialogOk")
    page.locator(".toast", has_text="Discarded").wait_for()
    page.wait_for_function("() => codeEditor()?.text() === 'def add(a, b):\\n    return a - b\\n'")
    assert not page.evaluate("document.querySelector('.tab.on').classList.contains('dirty')")
    page.wait_for_function("() => !Object.values(localStorage).some((v) => v.includes('my unsaved draft'))")
    page.reload()
    wait_editor(page)
    assert editor_text(page) == "def add(a, b):\n    return a - b\n"


def test_the_tab_of_a_file_that_is_gone_closes(page, server, session):
    changed(server, "new.py")
    open_app(page)
    page.evaluate("openFile('new.py')")
    page.locator("#editorTabs [data-tab='file:new.py']").wait_for()
    changes(page)
    ask_discard(page, "new.py")
    page.click("#dialogOk")
    page.locator(".toast", has_text="Discarded").wait_for()
    page.wait_for_function("() => !document.querySelector(\"#editorTabs [data-tab='file:new.py']\")")
    assert page.locator("#dialog").is_hidden()  # (closed without asking: there's nothing left to keep)


def test_discard_by_keyboard_and_focus_after(page, server, session):
    changed(server, "Makefile", "agent/core.py", "new.py")
    open_app(page)
    changes(page)
    page.locator("#gitList button[data-gitfile='agent/core.py']").focus()
    page.keyboard.press("Tab")  # the row's own Discard, its own tab stop
    assert page.evaluate("document.activeElement.dataset.gdiscard") == "agent/core.py"
    assert discard_button(page, "agent/core.py").evaluate("(b) => getComputedStyle(b).opacity") == "1"
    page.keyboard.press("Enter")
    page.locator("#dialog").wait_for()
    page.keyboard.press("Tab")  # (the dialog starts on Cancel: something destructive)
    page.keyboard.press("Enter")
    page.locator(".toast", has_text="Discarded").wait_for()
    page.wait_for_function("() => document.activeElement?.dataset?.gdiscard && "
                           "document.activeElement.dataset.gdiscard !== 'agent/core.py'")  # the next row's Discard
    audit(page, "Changes with Discard")


def test_discard_in_an_added_folder(page, server, session, tmp_path):
    api = make_git_repo(_api_folder(tmp_path))
    full = str(api.resolve())
    (api / "README.md").write_text("changed\n")
    server.store.update_session(session.id, folders=[full])
    open_app(page)
    changes(page)
    ask_discard(page, f"{full}/README.md")
    page.click("#dialogOk")
    page.locator(".toast", has_text="Discarded").wait_for()
    assert (api / "README.md").read_text() == "api\n"
