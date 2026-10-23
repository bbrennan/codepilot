"""GitHub access through the official `gh` CLI.

codepilot never sees a token: `gh` authenticates itself (macOS keychain after `gh auth login`, or GH_TOKEN),
the same login git and other tools on the machine use. Read-only commands run freely; commands that change
anything on GitHub need the user's approval; account/secret/admin commands are refused.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess

READ = {
    ("pr", "list"), ("pr", "view"), ("pr", "diff"), ("pr", "checks"), ("pr", "status"),
    ("issue", "list"), ("issue", "view"), ("issue", "status"),
    ("run", "list"), ("run", "view"), ("workflow", "list"), ("workflow", "view"),
    ("release", "list"), ("release", "view"), ("repo", "view"), ("label", "list"),
    ("search", "issues"), ("search", "prs"), ("search", "code"), ("search", "repos"), ("search", "commits"),
}
WRITE = {
    ("pr", "create"), ("pr", "comment"), ("pr", "review"), ("pr", "edit"), ("pr", "ready"), ("pr", "checkout"),
    ("issue", "create"), ("issue", "comment"), ("issue", "edit"), ("run", "rerun"),
}
API_WRITE_FLAGS = ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input")


def classify(argv: list[str]) -> str | None:
    """'read', 'write', or None (not allowed)."""
    if len(argv) >= 2 and (argv[0], argv[1]) in READ:
        return "read"
    if len(argv) >= 2 and (argv[0], argv[1]) in WRITE:
        return "write"
    if argv and argv[0] == "api" and len(argv) >= 2:
        method = "GET"
        for i, a in enumerate(argv):
            if a in ("-X", "--method") and i + 1 < len(argv):
                method = argv[i + 1].upper()
            elif a.startswith("--method="):
                method = a.split("=", 1)[1].upper()
        writes = any(a in API_WRITE_FLAGS[2:] or a.startswith(("--field=", "--raw-field=")) for a in argv)
        return "read" if method == "GET" and not writes else "write"
    return None


def env(host: str | None) -> dict:
    e = dict(os.environ)
    e.update({"GH_PROMPT_DISABLED": "1", "NO_COLOR": "1", "GH_PAGER": "cat", "GH_NO_UPDATE_NOTIFIER": "1"})
    if host:
        e["GH_HOST"] = host
    return e


def available() -> bool:
    return shutil.which("gh") is not None


def status(host: str | None) -> dict:
    """Who gh is logged in as (for the status bar and doctor)."""
    if not available():
        return {"available": False, "reason": "gh not installed (brew install gh)"}
    args = ["gh", "api", "user", "--jq", ".login"]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=15, env=env(host), check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": str(exc)}
    if proc.returncode != 0:
        hint = "gh auth login" + (f" --hostname {host}" if host else "")
        return {"available": False, "reason": f"not logged in: run {hint}"}
    return {"available": True, "user": proc.stdout.strip(), "host": host or "github.com"}


def run(cwd, args: str, host: str | None, timeout: int = 120) -> tuple[int, str]:
    argv = shlex.split(args)
    proc = subprocess.run(["gh", *argv], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env(host),
                          errors="replace", check=False)
    out = proc.stdout
    if proc.stderr.strip():
        out += ("\n" if out else "") + "[stderr]\n" + proc.stderr
    return proc.returncode, out


def pretty(out: str) -> str:
    """Compact JSON output from `gh ... --json` so it costs fewer tokens."""
    try:
        return json.dumps(json.loads(out), separators=(",", ":"))
    except (json.JSONDecodeError, ValueError):
        return out
