"""The git state the agent is told each turn.

Branch, uncommitted files and recent commits aren't enough to work safely: the agent also needs to know whether the
branch is behind its upstream (push would be rejected; rebase first), and above all whether a merge, rebase or
cherry-pick is half done, with which files conflicted. Without that it starts new work on top of a broken state.
Everything here is read locally; nothing fetches.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import procenv

IN_PROGRESS = (  # (marker in the git dir, operation, how to finish)
    ("rebase-merge", "rebase", "rebase"), ("rebase-apply", "rebase", "rebase"),
    ("MERGE_HEAD", "merge", "merge"), ("CHERRY_PICK_HEAD", "cherry-pick", "cherry-pick"),
    ("REVERT_HEAD", "revert", "revert"), ("BISECT_LOG", "bisect", None),
)


def _git(root: Path, *args: str) -> str:
    try:
        code, out, _ = procenv.run(["git", "--no-pager", "-C", str(root), *args], None, 10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.strip() if code == 0 else ""


def _files(names: list[str], limit: int = 10) -> str:
    return ", ".join(names[:limit]) + (f" +{len(names) - limit} more" if len(names) > limit else "")


def summary(root: Path | None) -> str:
    if root is None or not (root / ".git").exists():
        return ""
    lines = [_branch_line(root)]
    git_dir = Path(_git(root, "rev-parse", "--absolute-git-dir") or root / ".git")
    conflicted = _git(root, "diff", "--name-only", "--diff-filter=U").splitlines()
    for marker, op, finish in IN_PROGRESS:
        if (git_dir / marker).exists():
            n = len(conflicted)
            line = f"{op.upper()} IN PROGRESS"
            if n:
                line += f": {n} conflicted file{'s' if n != 1 else ''}: {_files(conflicted)}"
            if finish:
                line += (f". Resolve, `git add` the files, then `git {finish} --continue`, or `git {finish} --abort`"
                         " to undo it")
            lines.append(line + ".")
            break
    status = _git(root, "status", "--short").splitlines()
    lines.append(f"uncommitted ({len(status)}): " + _files([s[3:] for s in status], 25) if status
                 else "working tree clean")
    stashes = _git(root, "stash", "list").splitlines()
    if stashes:
        lines.append(f"stashes: {len(stashes)}")
    if log := _git(root, "log", "--oneline", "-5"):
        lines.append("recent commits:\n" + log)
    return "\n".join(lines)


def _branch_line(root: Path) -> str:
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")  # also names a branch with no commits yet
    if not branch:
        sha = _git(root, "rev-parse", "--short", "HEAD")
        return f"detached HEAD at {sha or '?'}"
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if not upstream:
        return f"branch {branch} (no upstream: not pushed yet)"
    counts = _git(root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD").split()
    behind, ahead = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
    if not ahead and not behind:
        return f"branch {branch}, tracking {upstream}: up to date (as of the last fetch)"
    state = ", ".join(x for x in (f"{ahead} ahead" if ahead else "", f"{behind} behind" if behind else "") if x)
    advice = "; pull or rebase before pushing" if behind else ""
    return f"branch {branch}, tracking {upstream}: {state} (as of the last fetch{advice})"
