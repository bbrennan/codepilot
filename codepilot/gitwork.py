"""The user's own git actions from the Changes view: what changed (and the Explorer's marks), Commit and Discard.

Separate from `gitcmd.py`, which says what the model's read-only git tool may run, so neither can grow into the other:
nothing the model can reach imports this module (tests/test_tools.py). Every command runs without a terminal
(`procenv`), never takes git's optional locks (the status runs in the background, beside commands you type), and reads
each path literally: `a*.txt` or `:notes` is a file's name, never a pattern.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from . import procenv

# Files listed for the page. A bigger tree (an un-ignored node_modules or .venv) is counted, and its folders still
# carry a dot, but its files aren't sent: thousands of rows help nobody, and the answer would be megabytes.
LIMIT = 2000

Runner = Callable[..., tuple[int, str, str]]  # procenv.run's: (argv, cwd, timeout, input=None) -> (code, out, err)
GIT = ["git", "--no-pager", "--no-optional-locks", "--literal-pathspecs"]


class GitError(Exception):
    """git refused, in its own words (trimmed), for the page to show as it is."""

    def __init__(self, message: str):
        super().__init__(message.strip()[:2000] or "git failed without saying why.")


def is_repo(root: Path) -> bool:
    """As everywhere in codepilot: git features need the folder to be the repository's root."""
    return (root / ".git").exists()


def _git(run: Runner, repo: Path, args: list[str], timeout: float = 60, input: str | None = None) -> str:
    code, out, err = run([*GIT, "-C", str(repo), *args], repo, timeout, **({} if input is None else {"input": input}))
    if code != 0:
        raise GitError(err or out)
    return out


def kind(code: str) -> str:
    """git's two status letters as what happened to the file."""
    if "U" in code or code in ("DD", "AA"):
        return "conflict"
    if code == "??":
        return "untracked"
    if "R" in code:
        return "renamed"
    if "D" in code:
        return "deleted"
    if "A" in code or "C" in code:
        return "added"
    return "modified"


def parse_status(out: str) -> list[dict]:
    """`git status --porcelain=v1 -z` as {path, code, kind} entries, with a rename's or copy's old name as `from`: real
    names (no quoting of spaces or accents), in either status column."""
    entries, files, i = out.split("\0"), [], 0
    while i < len(entries):
        entry = entries[i]
        if len(entry) > 3:
            code = entry[:2]
            f = {"path": entry[3:], "code": code.strip(), "kind": kind(code)}
            if any(c in "RC" for c in code) and i + 1 < len(entries):
                f["from"] = entries[i + 1]
            files.append(f)
        i += 2 if any(c in "RC" for c in entry[:2]) else 1
    return files


def changes(repo: Path, run: Runner = procenv.run) -> list[dict]:
    """Every changed file, each file of a new folder on its own (as Commit and Discard need them), however git is
    set to show untracked files."""
    return parse_status(_git(run, repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]))


def status(repo: Path, run: Runner = procenv.run) -> dict | None:
    """What the page shows: up to LIMIT files (tracked changes first), `total`, and every folder that holds one. None
    when the folder isn't a repository's root."""
    if not is_repo(repo):
        return None
    files = changes(repo, run)
    files.sort(key=lambda f: f["kind"] == "untracked")  # (stable: git's order within each)
    dirs: set[str] = set()
    for f in files:
        parts = f["path"].split("/")[:-1]
        dirs.update("/".join(parts[:n]) for n in range(1, len(parts) + 1))
    shallow = sorted(dirs, key=lambda d: (d.count("/"), d))[:LIMIT * 5]  # (the folders you see first keep their dot)
    return {"files": files[:LIMIT], "total": len(files), "dirs": shallow}


def _gitdir(repo: Path) -> Path | None:
    dot = repo / ".git"
    if dot.is_dir():
        return dot
    try:  # a worktree's or a submodule's: "gitdir: <path>"
        text = dot.read_text(errors="replace")
    except OSError:
        return None
    if not text.startswith("gitdir: "):
        return None
    found = (repo / text[len("gitdir: "):].strip()).resolve()
    return found if found.is_dir() else None


def stamp(repo: Path) -> str | None:
    """What changes when git's state does without any working file changing (a commit, staging, a reset, a checkout,
    all of which can be made in the terminal): the index, HEAD, the branch HEAD names, and packed refs. A commit leaves
    .git/HEAD as it was; it moves the branch. Stat only, no git process: the page asks every two seconds."""
    gitdir = _gitdir(repo)
    if gitdir is None:
        return None
    try:
        common = (gitdir / (gitdir / "commondir").read_text().strip()).resolve()
    except OSError:
        common = gitdir
    watched = [gitdir / "index", gitdir / "HEAD", common / "packed-refs"]
    try:
        head = (gitdir / "HEAD").read_text(errors="replace").strip()
    except OSError:
        head = ""
    if head.startswith("ref: "):
        ref = (common / head[len("ref: "):]).resolve()
        if common in ref.parents:  # (never a path outside the repository's own refs)
            watched.append(ref)
    parts = []
    for path in watched:
        try:
            st = path.stat()
            parts.append(f"{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append("-")
    return " ".join(parts)


# -- Commit ------------------------------------------------------------------------------------------------------------

HOOK_TIMEOUT = 120  # s: a commit runs your hooks (a linter, the tests), which can take a while


def _checked(repo: Path, paths: list[str], run: Runner, what: str) -> dict[str, dict]:
    """The entries for paths, each one git lists as changed (5.3): a path the page sends is never trusted as is."""
    entries = {f["path"]: f for f in changes(repo, run)}
    for p in paths:
        if p not in entries:
            raise GitError(f"{p} has no changes to {what} (git doesn't list it as changed).")
    return entries


def _staged(repo: Path, run: Runner, names: list[str]) -> str:
    """The index's entries for names, stage numbers included (a conflict has three), as update-index reads them."""
    return _git(run, repo, ["ls-files", "-s", "-z", "--", *names])


def _put_back(repo: Path, run: Runner, names: list[str], saved: str) -> None:
    """The index's entries for names as they were: each name taken out, then what was there written back."""
    zero = "0" * (64 if _git(run, repo, ["rev-parse", "--show-object-format"]).strip() == "sha256" else 40)
    lines = [f"0 {zero}\t{n}" for n in names] + [e for e in saved.split("\0") if e]
    _git(run, repo, ["update-index", "-z", "--index-info"], input="\0".join(lines) + "\0")


def _drop_stale_locks(repo: Path, since: float) -> None:
    """A commit stopped on its timeout leaves its index locks, and every git command after it would fail ("Another
    git process seems to be running"). Only the ones made since it started go: never a lock someone else holds."""
    gitdir = _gitdir(repo)
    for lock in [*(gitdir.glob("index.lock") if gitdir else []), *(gitdir.glob("next-index-*.lock") if gitdir else [])]:
        try:
            if lock.stat().st_mtime >= since:
                lock.unlink()
        except OSError:
            pass


def commit(repo: Path, message: str, paths: list[str], run: Runner = procenv.run,
           hook_timeout: float = HOOK_TIMEOUT) -> dict:
    """Commit the ticked files as they are on disk, new and deleted ones included, on the current branch, with the
    message exactly as typed and the user's own git identity. Never skips hooks, amends, pushes or changes branch.

    When every changed file is ticked there's no pathspec, so a merge can be concluded; with some, git commits only
    those (and refuses during a merge, in its own words). A refusal leaves the index as it was: the ticked paths'
    entries are saved before `git add` and written back."""
    if not message.strip():
        raise GitError("Write a commit message first.")
    if not paths:
        raise GitError("Tick at least one file to commit.")
    entries = _checked(repo, paths, run, "commit")
    names = list(dict.fromkeys(n for p in paths for n in (p, entries[p].get("from")) if n))  # (a rename: both)
    every = {n for f in entries.values() for n in (f["path"], f.get("from")) if n}
    saved = _staged(repo, run, names)
    since = time.time() - 1
    in_index = {e.split("\t", 1)[1] for e in saved.split("\0") if "\t" in e}
    # A name that's on disk or in the index is added (or its deletion staged); a staged rename's old name is in
    # neither, and git would refuse it, but the commit below still names it.
    there = [n for n in names if (repo / n).exists() or (repo / n).is_symlink() or n in in_index]
    if there:
        _git(run, repo, ["add", "--all", "--", *there])
    try:
        # --cleanup=verbatim: as typed (git would strip "#" lines and trailing spaces, whatever commit.cleanup says).
        _git(run, repo, ["commit", "--quiet", "--cleanup=verbatim", "--message", message,
                         *([] if set(names) >= every else ["--", *names])], timeout=hook_timeout)
    except subprocess.TimeoutExpired:
        _drop_stale_locks(repo, since)
        _put_back(repo, run, names, saved)
        raise GitError(f"git commit took longer than {hook_timeout:g} s (a hook?) and was stopped.") from None
    except GitError:
        _put_back(repo, run, names, saved)
        raise
    hash_, _, subject = _git(run, repo, ["log", "-1", "--format=%h%x00%s"]).rstrip("\n").partition("\0")
    return {"hash": hash_, "subject": subject}
