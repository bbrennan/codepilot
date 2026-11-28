"""Temporary git repositories for tests: the Changes view's actions commit and discard, so never in a real one."""

import subprocess


def make_git_repo(root):
    """root as a repository with one commit of everything in it, as CI can make it: an invented identity and no
    signing, set in that repository only (CI has no identity; a developer's own config mustn't decide a test)."""
    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    if not (root / ".git").exists():
        git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/main")
    for key, value in (("user.name", "Ada Example"), ("user.email", "ada@example.invalid"),
                       ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        git("config", key, value)
    git("add", "-A")
    git("commit", "-q", "-m", "start")
    return root
