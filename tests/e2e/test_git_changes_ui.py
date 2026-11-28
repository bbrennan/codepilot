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
