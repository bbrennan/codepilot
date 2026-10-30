"""What the read-only git tool may run.

Some subcommands only ever read (status, log, diff, ...). Others read or write depending on their arguments:
`git branch` lists branches, but `git branch -D x` deletes one and `git branch x` creates one. Those get a
validator that allows the reading forms only, so the tool can't change the repository without the user's approval
(writes go through run_command, which always asks).
"""

from __future__ import annotations

ALWAYS_READ = {"status", "diff", "log", "show", "blame", "rev-parse", "ls-files", "shortlog", "rev-list", "merge-base"}
BANNED_ARGS = ("--output", "--exec", "-c", "--git-dir", "--work-tree", "--ext-diff")


class NotReadOnly(ValueError):
    pass


def _branch(args: list[str]) -> None:
    flags = {"-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "-l", "--list", "--show-current",
             "--no-color", "--color", "--column", "--no-column", "-i", "--ignore-case", "--omit-empty"}
    with_value = {"--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "--sort", "--format",
                  "--abbrev"}
    listing = False
    i = 0
    while i < len(args):
        a = args[i]
        name = a.split("=", 1)[0]
        if name in with_value:
            i += 1 if "=" in a else 2  # its value isn't a branch name to create
            continue
        if a.startswith("--"):
            if name not in flags:
                raise NotReadOnly(f"git branch {a} changes branches")
            listing = listing or name == "--list"
        elif a.startswith("-") and len(a) > 1:
            if set(a[1:]) - set("arvli"):  # e.g. -d, -D, -m, -M, -c, -C, -f, -u, -t, and clusters like -vD
                raise NotReadOnly(f"git branch {a} changes branches")
            listing = listing or "l" in a
        elif not listing:
            raise NotReadOnly(f"git branch {a} creates a branch")
        i += 1


def _stash(args: list[str]) -> None:
    if not args or args[0] not in ("list", "show"):
        raise NotReadOnly("only `git stash list` and `git stash show` are read-only")


def _remote(args: list[str]) -> None:
    if args and args[0] not in ("-v", "--verbose", "get-url"):
        raise NotReadOnly("only `git remote`, `git remote -v` and `git remote get-url` are read-only")


def _reflog(args: list[str]) -> None:
    if args and args[0] in ("expire", "delete", "drop"):
        raise NotReadOnly(f"git reflog {args[0]} changes the reflog")


CHECKS = {"branch": _branch, "stash": _stash, "remote": _remote, "reflog": _reflog}
ALLOWED = sorted(ALWAYS_READ | set(CHECKS))


def check_read_only(argv: list[str]) -> None:
    """Raise NotReadOnly unless `git <argv>` can only read."""
    if not argv or argv[0] not in ALWAYS_READ and argv[0] not in CHECKS:
        raise NotReadOnly(f"only read-only git subcommands are allowed: {ALLOWED}")
    for arg in argv:
        if arg in BANNED_ARGS or any(arg.startswith(b + "=") for b in BANNED_ARGS):
            raise NotReadOnly(f"git argument {arg!r} is not allowed")
    if argv[0] in CHECKS:
        CHECKS[argv[0]](argv[1:])
