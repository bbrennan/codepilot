"""The user's own git actions (spec git-changes): gitwork.py, against real repositories made for each test."""

import os
import subprocess

import pytest

from codepilot import gitwork, procenv


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


# -- task 2.1: Commit --------------------------------------------------------------------------------------------------


def committed_files(repo, rev="HEAD"):
    return sorted(git(repo, "show", "--no-renames", "--name-only", "--format=", rev).split("\n")[:-1])


def index(repo):
    """The whole index, stage numbers included: what "as it found it" means."""
    return git(repo, "ls-files", "-s")


def hook(repo, name, body):
    path = repo / ".git" / "hooks" / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def test_only_the_ticked_files_are_committed_and_a_star_is_a_name(git_repo):
    """git reads `a*.txt` as a pattern that `ab.txt` matches: ticking only `a*.txt` must commit only that file."""
    for name in ("a*.txt", "ab.txt"):
        (git_repo / name).write_text("one\n")
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "-qm", "both")
    for name in ("a*.txt", "ab.txt"):
        (git_repo / name).write_text("two\n")
    gitwork.commit(git_repo, "only the star", ["a*.txt"])
    assert committed_files(git_repo) == ["a*.txt"]
    assert kinds(git_repo) == {"ab.txt": "modified"}


@pytest.mark.parametrize("name", [":colon.txt", ":(glob)x.txt", "q?.txt", "[ab].txt"])
def test_a_name_git_would_read_as_magic_or_a_pattern_commits_as_itself(git_repo, name):
    (git_repo / name).write_text("new\n")
    (git_repo / "qa.txt").write_text("not me\n")  # (`q?.txt` would match it)
    gitwork.commit(git_repo, "add it", [name])
    assert committed_files(git_repo) == [name]
    assert "qa.txt" in kinds(git_repo)


def test_new_and_deleted_files_are_committed_and_the_rest_stays_as_it_was(git_repo):
    (git_repo / "new.py").write_text("x = 1\n")
    (git_repo / "Makefile").unlink()
    (git_repo / "agent" / "core.py").write_text("not ticked\n")
    (git_repo / "tests" / "test_core.py").write_text("staged before, not ticked\n")
    git(git_repo, "add", "tests/test_core.py")
    gitwork.commit(git_repo, "new and gone", ["new.py", "Makefile"])
    assert committed_files(git_repo) == ["Makefile", "new.py"]
    assert kinds(git_repo) == {"agent/core.py": "modified", "tests/test_core.py": "modified"}
    assert git(git_repo, "diff", "--cached", "--name-only") == "tests/test_core.py\n"  # still staged


def test_a_ticked_file_is_committed_as_it_is_on_disk_not_as_it_was_staged(git_repo):
    core = git_repo / "agent" / "core.py"
    core.write_text("staged\n")
    git(git_repo, "add", "agent/core.py")
    core.write_text("on disk\n")
    gitwork.commit(git_repo, "as on disk", ["agent/core.py"])
    assert git(git_repo, "show", "HEAD:agent/core.py") == "on disk\n"


def test_a_rename_commits_both_of_its_names(git_repo):
    git(git_repo, "mv", "Makefile", "build.mk")
    gitwork.commit(git_repo, "rename", ["build.mk"])
    assert committed_files(git_repo) == ["Makefile", "build.mk"] and kinds(git_repo) == {}


def test_the_message_is_kept_exactly_as_typed_with_nothing_added(git_repo):
    message = "Fix the sign  \n\n\n# not a comment: kept\n    indented line\n\ntrailing blank lines\n\n"
    (git_repo / "Makefile").write_text("changed\n")
    gitwork.commit(git_repo, message, ["Makefile"])
    raw = git(git_repo, "cat-file", "commit", "HEAD")
    assert raw.split("\n\n", 1)[1] == message  # no cleanup, no trailer, no sign-off


def test_the_commit_is_the_users_own_identity(git_repo):
    (git_repo / "Makefile").write_text("changed\n")
    gitwork.commit(git_repo, "mine", ["Makefile"])
    assert git(git_repo, "log", "-1", "--format=%an <%ae>|%cn <%ce>") == \
        "Ada Example <ada@example.invalid>|Ada Example <ada@example.invalid>\n"


def test_the_answer_is_the_short_hash_and_the_subject(git_repo):
    (git_repo / "Makefile").write_text("changed\n")
    got = gitwork.commit(git_repo, "Subject line\n\nBody text", ["Makefile"])
    assert got == {"hash": git(git_repo, "rev-parse", "--short", "HEAD").strip(), "subject": "Subject line"}


@pytest.mark.parametrize("message", ["", "   ", "\n\n  \n"])
def test_a_blank_message_is_refused(git_repo, message):
    (git_repo / "Makefile").write_text("changed\n")
    with pytest.raises(gitwork.GitError, match="message"):
        gitwork.commit(git_repo, message, ["Makefile"])
    assert kinds(git_repo) == {"Makefile": "modified"}


def test_nothing_ticked_is_refused(git_repo):
    (git_repo / "Makefile").write_text("changed\n")
    with pytest.raises(gitwork.GitError, match="Tick"):
        gitwork.commit(git_repo, "nothing", [])


@pytest.mark.parametrize("path", ["agent/core.py", "nope.txt", "../outside.txt", "agent"])
def test_a_path_git_doesnt_list_as_changed_is_refused(git_repo, path):
    (git_repo / "Makefile").write_text("changed\n")
    head, before = git(git_repo, "rev-parse", "HEAD"), index(git_repo)
    with pytest.raises(gitwork.GitError, match="no changes"):
        gitwork.commit(git_repo, "sneak", ["Makefile", path])
    assert git(git_repo, "rev-parse", "HEAD") == head and index(git_repo) == before


def test_a_failing_hook_is_shown_in_its_own_words_and_leaves_the_index_as_it_found_it(git_repo):
    hook(git_repo, "pre-commit", "echo 'lint: 3 problems in core.py' >&2\nexit 1\n")
    (git_repo / "new.py").write_text("x = 1\n")  # untracked: staged by the commit, then unstaged again
    core = git_repo / "agent" / "core.py"
    core.write_text("part staged\n")
    git(git_repo, "add", "agent/core.py")
    core.write_text("part staged\nand more on disk\n")  # staged before, ticked: its staged version comes back
    (git_repo / "Makefile").write_text("staged, not ticked\n")
    git(git_repo, "add", "Makefile")
    before, head = index(git_repo), git(git_repo, "rev-parse", "HEAD")
    with pytest.raises(gitwork.GitError, match="lint: 3 problems in core.py"):
        gitwork.commit(git_repo, "refused", ["new.py", "agent/core.py"])
    assert index(git_repo) == before and git(git_repo, "rev-parse", "HEAD") == head
    assert git(git_repo, "show", ":agent/core.py") == "part staged\n"
    assert core.read_text() == "part staged\nand more on disk\n" and (git_repo / "new.py").exists()


def test_hooks_run(git_repo):
    hook(git_repo, "pre-commit", f"touch '{git_repo / 'hook-ran'}'\n")
    (git_repo / "Makefile").write_text("changed\n")
    gitwork.commit(git_repo, "with hooks", ["Makefile"])
    assert (git_repo / "hook-ran").exists()


def test_a_hook_that_takes_too_long_is_stopped_and_named(git_repo):
    hook(git_repo, "pre-commit", "sleep 30\n")
    (git_repo / "Makefile").write_text("changed\n")
    (git_repo / "README.md").write_text("not ticked\n")  # (a partial commit: git holds its index locks over the hook)
    before = index(git_repo)
    with pytest.raises(gitwork.GitError, match="took longer than 1 s"):
        gitwork.commit(git_repo, "slow", ["Makefile"], hook_timeout=1)
    assert index(git_repo) == before
    assert not list((git_repo / ".git").glob("*.lock"))  # (or the next git command typed would fail)
    git(git_repo, "add", "Makefile")


def _conflict(repo):
    git(repo, "switch", "-q", "-c", "other")
    (repo / "Makefile").write_text("theirs\n")
    git(repo, "commit", "-qam", "theirs")
    git(repo, "switch", "-q", "-")
    (repo / "Makefile").write_text("ours\n")
    (repo / "agent" / "core.py").write_text("ours too\n")
    git(repo, "commit", "-qam", "ours")
    subprocess.run(["git", "-C", str(repo), "merge", "-q", "other"], capture_output=True)
    (repo / "Makefile").write_text("resolved\n")


def test_all_files_ticked_concludes_a_merge(git_repo):
    _conflict(git_repo)
    gitwork.commit(git_repo, "Merge other", [f["path"] for f in gitwork.changes(git_repo)])
    assert len(git(git_repo, "log", "-1", "--format=%P").split()) == 2 and kinds(git_repo) == {}


def test_some_files_ticked_during_a_merge_is_gits_refusal_and_changes_nothing(git_repo):
    _conflict(git_repo)
    (git_repo / "README.md").write_text("another change\n")
    before = index(git_repo)
    with pytest.raises(gitwork.GitError, match="partial commit|merge"):
        gitwork.commit(git_repo, "half", ["Makefile"])
    assert index(git_repo) == before and (git_repo / ".git" / "MERGE_HEAD").exists()


def test_the_first_commit_of_a_new_repository(tmp_path, git_isolated):
    repo = tmp_path / "fresh"
    repo.mkdir()
    git(repo, "init", "-q")
    for key, value in (("user.name", "Ada Example"), ("user.email", "ada@example.invalid"),
                       ("commit.gpgsign", "false")):
        git(repo, "config", key, value)
    (repo / "a.txt").write_text("a\n")
    (repo / "b.txt").write_text("b\n")
    gitwork.commit(repo, "first", ["a.txt"])
    assert committed_files(repo) == ["a.txt"] and kinds(repo) == {"b.txt": "untracked"}


def test_a_refused_first_commit_leaves_the_index_empty(tmp_path, git_isolated):
    repo = tmp_path / "fresh"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "commit.gpgsign", "false")
    hook(repo, "pre-commit", "exit 1\n")
    (repo / "a.txt").write_text("a\n")
    with pytest.raises(gitwork.GitError):
        gitwork.commit(repo, "first", ["a.txt"])
    assert index(repo) == "" and kinds(repo) == {"a.txt": "untracked"}


def test_never_skips_hooks_amends_pushes_or_changes_branch(git_repo):
    """Every command it runs, as run: nothing requirement 3.5 rules out, and each one literal and lock-free."""
    seen = []

    def spy(argv, cwd, timeout, **kw):
        seen.append(argv)
        return procenv.run(argv, cwd, timeout, **kw)

    (git_repo / "Makefile").write_text("changed\n")
    (git_repo / "new.py").write_text("x\n")
    gitwork.commit(git_repo, "spied", ["Makefile", "new.py"], run=spy)
    hook(git_repo, "pre-commit", "exit 1\n")
    (git_repo / "Makefile").write_text("again\n")
    with pytest.raises(gitwork.GitError):
        gitwork.commit(git_repo, "refused", ["Makefile"], run=spy)
    banned = {"--no-verify", "-n", "--amend", "push", "checkout", "switch", "branch", "--force", "-f", "rebase",
              "reset --hard", "--author", "-c"}
    for argv in seen:
        assert argv[:4] == ["git", "--no-pager", "--no-optional-locks", "--literal-pathspecs"], argv
        assert not banned & set(argv[4:]), argv
        assert "--hard" not in argv
