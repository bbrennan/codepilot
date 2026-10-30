"""The git state the agent is told each turn: enough to avoid bad pushes, surprise conflicts and lost rebases."""

import os
import subprocess

from codepilot import gitstate


def git_env(cwd):
    return {**os.environ, "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1", "GIT_EDITOR": ":",  # no user git config
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}


def sh(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=git_env(cwd))


def repo_with_commit(path):
    path.mkdir(parents=True, exist_ok=True)
    sh(path, "init", "-q", "-b", "main")
    (path / "f.txt").write_text("one\n")
    sh(path, "add", "f.txt")
    sh(path, "commit", "-q", "-m", "first")
    return path


def test_no_repository_means_no_summary(tmp_path):
    assert gitstate.summary(tmp_path) == ""


def test_a_local_branch_without_upstream(tmp_path):
    root = repo_with_commit(tmp_path / "r")
    text = gitstate.summary(root)
    assert text.splitlines()[0] == "branch main (no upstream: not pushed yet)"
    assert "working tree clean" in text and "first" in text


def test_ahead_and_behind_its_upstream(tmp_path):
    origin = tmp_path / "origin.git"
    sh(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    mine = repo_with_commit(tmp_path / "mine")
    sh(mine, "remote", "add", "origin", str(origin))
    sh(mine, "push", "-q", "-u", "origin", "main")
    theirs = tmp_path / "theirs"
    sh(tmp_path, "clone", "-q", str(origin), str(theirs))
    (theirs / "g.txt").write_text("theirs\n")
    sh(theirs, "add", "g.txt")
    sh(theirs, "commit", "-q", "-m", "their change")
    sh(theirs, "push", "-q", "origin", "main")
    (mine / "h.txt").write_text("mine\n")
    sh(mine, "add", "h.txt")
    sh(mine, "commit", "-q", "-m", "my change")
    sh(mine, "fetch", "-q", "origin")
    first = gitstate.summary(mine).splitlines()[0]
    assert first == ("branch main, tracking origin/main: 1 ahead, 1 behind (as of the last fetch; "
                     "pull or rebase before pushing)")


def test_a_merge_conflict_in_progress_is_spelled_out(tmp_path):
    root = repo_with_commit(tmp_path / "r")
    sh(root, "checkout", "-q", "-b", "other")
    (root / "f.txt").write_text("other\n")
    sh(root, "commit", "-q", "-am", "other side")
    sh(root, "checkout", "-q", "main")
    (root / "f.txt").write_text("main\n")
    sh(root, "commit", "-q", "-am", "main side")
    subprocess.run(["git", "-C", str(root), "merge", "other"], capture_output=True, env=git_env(root))  # conflicts
    text = gitstate.summary(root)
    assert "MERGE IN PROGRESS: 1 conflicted file: f.txt" in text
    assert "git merge --continue" in text and "git merge --abort" in text


def test_a_rebase_in_progress_and_stashes(tmp_path):
    root = repo_with_commit(tmp_path / "r")
    (root / "f.txt").write_text("stashed\n")
    sh(root, "stash", "-q")
    sh(root, "checkout", "-q", "-b", "other")
    (root / "f.txt").write_text("other\n")
    sh(root, "commit", "-q", "-am", "other side")
    sh(root, "checkout", "-q", "main")
    (root / "f.txt").write_text("main\n")
    sh(root, "commit", "-q", "-am", "main side")
    subprocess.run(["git", "-C", str(root), "rebase", "other"], capture_output=True, env=git_env(root))  # conflicts
    text = gitstate.summary(root)
    assert "REBASE IN PROGRESS: 1 conflicted file: f.txt" in text and "git rebase --continue" in text
    assert "stashes: 1" in text


def test_detached_head(tmp_path):
    root = repo_with_commit(tmp_path / "r")
    sh(root, "checkout", "-q", "--detach")
    assert gitstate.summary(root).startswith("detached HEAD at ")
