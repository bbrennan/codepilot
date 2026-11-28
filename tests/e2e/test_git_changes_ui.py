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
    assert "Renamed from tests/test_core.py" in row(page, "tests/test_add.py").locator("button").get_attribute("title")
    assert page.locator("#gitList .git-row").count() == 4  # no "??", nothing twice
    assert row(page, "new.py").get_by_role("button", name="new.py, untracked", exact=True).count() == 1  # (as read)
    audit(page, "Changes with git rows")


def test_a_name_with_spaces_opens_its_own_file(page, server, session):
    (server.repo / "notes with spaces.txt").write_text("the real one\n")
    open_app(page)
    changes(page)
    row(page, "notes with spaces.txt").locator("button").click()
    page.locator("#editor code", has_text="the real one").wait_for()
    assert page.evaluate("state.active") == "file:notes with spaces.txt"


def test_a_name_with_spaces_opens_by_keyboard_too(page, server, session):
    (server.repo / "notes with spaces.txt").write_text("the real one\n")
    open_app(page)
    changes(page)
    row(page, "notes with spaces.txt").locator("button").focus()
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
    row(page, "Makefile").locator("button").click()
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
    row(page, f"{full}/my file é.py").locator("button").click()
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
