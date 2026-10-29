#!/usr/bin/env python3
"""PreToolUse hook for Bash: enforce CLAUDE.md's git rules. Exit 2 blocks the command and tells the model why.

Blocked: commit/push while on main or develop, pushing to them from anywhere, force pushes, and --no-verify.
"""

import json
import re
import shlex
import subprocess
import sys

PROTECTED = {"main", "develop"}
SEGMENT = re.compile(r"&&|\|\||;|\||\n")
OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree"}


def git_args(segment):
    """('commit', [args...]) for a `git ...` segment, else None."""
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return None
    if "git" not in tokens:
        return None
    rest = tokens[tokens.index("git") + 1:]
    while rest and rest[0].startswith("-"):
        rest = rest[2:] if rest[0] in OPTS_WITH_VALUE else rest[1:]
    return (rest[0], rest[1:]) if rest else None


def current_branch(cwd):
    try:
        out = subprocess.run(["git", "-C", cwd or ".", "branch", "--show-current"], capture_output=True, text=True,
                             timeout=10)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def problem(sub, args, branch):
    if "--no-verify" in args or (sub == "commit" and "-n" in args):
        return "--no-verify skips the checks; fix what they report instead."
    if sub == "push":
        flags = [a for a in args if a.startswith("-") and not a.startswith("--")]
        if "--force" in args or any("f" in f[1:] for f in flags):
            return "never force-push; make a new commit or open a PR."
        positional = [a for a in args if not a.startswith("-")]
        for ref in positional[1:]:  # positional[0] is the remote
            if ref.startswith("+"):
                return "never force-push (+refspec)."
            dest = ref.split(":")[-1].removeprefix("refs/heads/")
            if dest in PROTECTED:
                return f"never push to {dest} directly; open a PR from a feature/** or fix/** branch."
    if sub in {"commit", "push"} and branch in PROTECTED:
        return f"you are on {branch}. Branch first: git switch -c fix/<topic> (or feature/<topic>), then open a PR."
    return None


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        return 0
    command = data.get("tool_input", {}).get("command", "")
    branch = None
    for segment in SEGMENT.split(command):
        parsed = git_args(segment)
        if not parsed or parsed[0] not in {"commit", "push"}:
            continue
        if branch is None:
            branch = current_branch(data.get("cwd"))
        why = problem(*parsed, branch)
        if why:
            print(f"Blocked by .claude/hooks/guard_git.py (CLAUDE.md): {why}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
