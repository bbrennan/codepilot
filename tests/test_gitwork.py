"""The user's own git actions (spec git-changes): gitwork.py, against real repositories made for each test."""

import os
import subprocess

import pytest

from codepilot import gitwork


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True, text=True).stdout


def kinds(repo):
    return {f["path"]: f["kind"] for f in gitwork.status(repo)["files"]}


# -- task 1.1: what changed ---------------------------------------------------------------------------------------------


def test_each_kind_of_change_is_named(git_repo):
    (git_repo / "agent" / "core.py").write_text("def add(a, b):\n    return a + b\n")
    (git_repo / "new.py").write_text("x = 1\n")
    (git_repo / "staged.py").write_text("y = 2\n")
    git(git_repo, "add", "staged.py")
    (git_repo / "Makefile").unlink()
    git(git_repo, "mv", "tests/test_core.py", "tests/test_add.py")
    assert kinds(git_repo) == {"agent/core.py": "modified", "new.py": "untracked", "staged.py": "added",
                               "Makefile": "deleted", "tests/test_add.py": "renamed"}
    [moved] = [f for f in gitwork.status(git_repo)["files"] if f["kind"] == "renamed"]
    assert moved["from"] == "tests/test_core.py"


def test_a_conflict_is_named_as_one(git_repo):
    git(git_repo, "switch", "-q", "-c", "other")
    (git_repo / "Makefile").write_text("theirs\n")
    git(git_repo, "commit", "-qam", "theirs")
    git(git_repo, "switch", "-q", "-")
    (git_repo / "Makefile").write_text("ours\n")
    git(git_repo, "commit", "-qam", "ours")
    git(git_repo, "merge", "-q", "other", check=False)
    assert kinds(git_repo) == {"Makefile": "conflict"}


def test_names_with_spaces_and_accents_are_their_real_names(git_repo):
    (git_repo / "notes with spaces.txt").write_text("a\n")
    (git_repo / "café.py").write_text("b\n")
    assert set(kinds(git_repo)) == {"notes with spaces.txt", "café.py"}


def test_every_file_in_a_new_folder_is_listed_whatever_git_is_set_to(git_repo):
    """Marks, ticks and Discard need each file, not git's one `new/` entry; a setting mustn't hide them."""
    git(git_repo, "config", "status.showUntrackedFiles", "no")
    (git_repo / "new" / "deep").mkdir(parents=True)
    (git_repo / "new" / "a.py").write_text("a\n")
    (git_repo / "new" / "deep" / "b.py").write_text("b\n")
    got = gitwork.status(git_repo)
    assert {f["path"] for f in got["files"]} == {"new/a.py", "new/deep/b.py"}
    assert set(got["dirs"]) == {"new", "new/deep"}


def test_a_very_large_untracked_tree_is_counted_not_listed(git_repo, monkeypatch):
    monkeypatch.setattr(gitwork, "LIMIT", 3)
    (git_repo / "node_modules" / "pkg").mkdir(parents=True)
    for i in range(5):
        (git_repo / "node_modules" / "pkg" / f"f{i}.js").write_text("x\n")
    (git_repo / "agent" / "core.py").write_text("changed\n")
    got = gitwork.status(git_repo)
    assert len(got["files"]) == 3 and got["total"] == 6
    assert got["files"][0]["path"] == "agent/core.py"  # tracked changes first: they are what you came for
    assert {"agent", "node_modules", "node_modules/pkg"} <= set(got["dirs"])  # the folders still say so


def test_the_status_never_takes_gits_optional_locks(git_repo):
    """It runs in the background: it must not rewrite the index under a command typed in the terminal."""
    core = git_repo / "agent" / "core.py"
    index = git_repo / ".git" / "index"
    os.utime(core, ns=(core.stat().st_mtime_ns + 5_000_000_000,) * 2)  # same text, newer stat: git would refresh it
    before = index.stat().st_mtime_ns
    gitwork.status(git_repo)
    assert index.stat().st_mtime_ns == before
    git(git_repo, "status", "--porcelain")  # (and git itself does, so the test means something)
    assert index.stat().st_mtime_ns != before


def test_a_rename_in_either_status_column_keeps_its_old_name():
    out = " R new.py\0old.py\0R  moved.py\0was.py\0?? my file é.py\0"
    assert gitwork.parse_status(out) == [
        {"path": "new.py", "code": "R", "kind": "renamed", "from": "old.py"},
        {"path": "moved.py", "code": "R", "kind": "renamed", "from": "was.py"},
        {"path": "my file é.py", "code": "??", "kind": "untracked"}]


def test_a_folder_that_isnt_a_repository_has_no_status(tmp_path):
    assert gitwork.status(tmp_path) is None


# -- task 1.3: what the disk poll watches ------------------------------------------------------------------------------


def test_the_stamp_changes_with_a_commit_or_staging_made_in_the_terminal(git_repo):
    """A commit changes no working file, and not .git/HEAD either: the branch it names."""
    first = gitwork.stamp(git_repo)
    assert first and gitwork.stamp(git_repo) == first
    (git_repo / "agent" / "core.py").write_text("changed\n")
    git(git_repo, "add", "-A")
    staged = gitwork.stamp(git_repo)
    assert staged != first
    git(git_repo, "commit", "-qm", "in the terminal")
    assert gitwork.stamp(git_repo) != staged


def test_a_folder_that_isnt_a_repository_has_no_stamp(tmp_path):
    assert gitwork.stamp(tmp_path) is None


@pytest.mark.parametrize("head", ["ref: ../../../etc/passwd\n", "ref: refs/heads/../../../../x\n"])
def test_the_stamp_never_reads_outside_the_repository(git_repo, head):
    (git_repo / ".git" / "HEAD").write_text(head)
    assert gitwork.stamp(git_repo)  # (stamped without the ref)
