"""The user's own git actions from the Changes view: what changed (and the Explorer's marks), Commit and Discard.

Separate from `gitcmd.py`, which says what the model's read-only git tool may run, so neither can grow into the other:
nothing the model can reach imports this module (tests/test_tools.py). Every command runs without a terminal
(`procenv`), never takes git's optional locks (the status runs in the background, beside commands you type), and reads
each path literally: `a*.txt` or `:notes` is a file's name, never a pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import procenv

# Files listed for the page. A bigger tree (an un-ignored node_modules or .venv) is counted, and its folders still
# carry a dot, but its files aren't sent: thousands of rows help nobody, and the answer would be megabytes.
LIMIT = 2000

Runner = Callable[[list[str], Path, float], tuple[int, str, str]]
GIT = ["git", "--no-pager", "--no-optional-locks", "--literal-pathspecs"]


class GitError(Exception):
    """git refused, in its own words (trimmed), for the page to show as it is."""

    def __init__(self, message: str):
        super().__init__(message.strip()[:2000] or "git failed without saying why.")


def is_repo(root: Path) -> bool:
    """As everywhere in codepilot: git features need the folder to be the repository's root."""
    return (root / ".git").exists()


def _git(run: Runner, repo: Path, args: list[str], timeout: float = 60) -> str:
    code, out, err = run([*GIT, "-C", str(repo), *args], repo, timeout)
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
