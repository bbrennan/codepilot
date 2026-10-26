"""Report a problem: a diagnostics report to save, and a short redacted summary for a GitHub issue.

The report (downloaded to your machine) has what's needed to debug: code version, platform, settings
without secrets, the session's state and events, recent warnings and errors, and the server log's tail.
The GitHub issue gets only a short summary: codepilot's repo is public, so no conversation, code or file
contents ever go there, and you review it on GitHub before submitting.

Everything passes through redact(): API keys and tokens, AWS credentials, passwords in URLs, email
addresses, and your home folder (which usually contains your user name).
"""

from __future__ import annotations

import collections
import json
import logging
import platform
import re
import sys
import time
import urllib.parse
from pathlib import Path

ISSUES_REPO = "bbrennan/codepilot"
MAX_ISSUE_URL = 7500  # GitHub rejects much longer prefilled URLs
SECRET_PATTERNS = [
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[aws-access-key]"),
    (re.compile(r"(?i)(aws_secret_access_key|aws_session_token|secret|password|passwd|token|api[_-]?key)"
                r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1\2[redacted]"),
    (re.compile(r"\bsk-ant-[\w-]{10,}"), "[anthropic-key]"),
    (re.compile(r"\bsk-[\w-]{20,}"), "[api-key]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[github-token]"),
    (re.compile(r"\bxox[abprs]-[\w-]{10,}"), "[slack-token]"),
    (re.compile(r"(?i)\bbearer\s+[\w.\-~+/=]{12,}"), "Bearer [redacted]"),
    (re.compile(r"(https?://)[^\s/:@]+:[^\s/@]+@"), r"\1[user]:[redacted]@"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"), "[jwt]"),
]


def redact(text: str, extra: tuple[str, ...] = ()) -> str:
    text = str(text)
    for secret in extra:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[redacted]")
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    home = str(Path.home())
    return text.replace(home, "~") if len(home) > 1 else text


def redact_obj(obj, extra: tuple[str, ...] = ()):
    if isinstance(obj, str):
        return redact(obj, extra)
    if isinstance(obj, dict):
        return {k: redact_obj(v, extra) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v, extra) for v in obj]
    return obj


_PROBLEMS: RecentProblems | None = None


def problems() -> RecentProblems:
    """The process-wide buffer of recent warnings and errors (installed once on the root logger)."""
    global _PROBLEMS
    if _PROBLEMS is None:
        _PROBLEMS = RecentProblems()
        logging.getLogger().addHandler(_PROBLEMS)
    return _PROBLEMS


class RecentProblems(logging.Handler):
    """Keeps the last warnings and errors the server logged, for reports."""

    def __init__(self, size: int = 200):
        super().__init__(logging.WARNING)
        self.records: collections.deque = collections.deque(maxlen=size)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append({"time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
                                 "level": record.levelname, "logger": record.name,
                                 "message": record.getMessage()[:4000]})
        except Exception:  # noqa: BLE001 - logging must never fail
            pass


def safe_settings(cfg) -> dict:
    """Configuration with no keys or tokens (keys live in the environment and are never read here)."""
    keep = ("provider", "region", "bedrock_api", "prompt_cache", "thinking", "effort", "models", "default_tier",
            "max_tokens", "test_cmd", "eval_cmd", "trace_dirs", "auto_approve_tests", "auto_apply_edits",
            "terminal", "github", "context_tokens", "prune_at", "compact_at", "max_steps", "web_tools",
            "system_certs", "latest_models")
    out = {k: getattr(cfg, k, None) for k in keep}
    out["profile_set"] = bool(getattr(cfg, "profile", None))
    out["brave_key_set"] = bool(getattr(cfg, "brave_api_key", ""))
    out["context7_key_set"] = bool(getattr(cfg, "context7_api_key", ""))
    out["anthropic_base_url_set"] = bool(getattr(cfg, "anthropic_base_url", None))
    out["openai_base_url_set"] = bool(getattr(cfg, "openai_base_url", None))
    return out


def log_tail(path: Path, lines: int = 120) -> list[str]:
    try:
        return path.read_text(errors="replace").splitlines()[-lines:]
    except OSError:
        return []


def issue_markdown(report: dict, description: str, title: str) -> str:
    """A short, redacted summary for a public GitHub issue (never conversation or code)."""
    env = report["environment"]
    sess = report.get("session") or {}
    problems = report.get("server_problems", [])[-6:]
    page_errors = report.get("client", {}).get("errors", [])[-6:]
    lines = [
        "### What happened", "", redact(description.strip()) or "_(describe the problem)_", "",
        "### Environment", "",
        f"- codepilot version: `{env['version']}`{' (server running older code: restart it)' if env['stale'] else ''}",
        f"- OS: {env['os']} · Python {env['python']} · browser: {report.get('client', {}).get('browser', '?')}",
        f"- provider: `{report['settings']['provider']}` · tier: `{sess.get('tier', '?')}` · mode: "
        f"`{sess.get('mode', '?')}` · model: `{sess.get('model') or '(tier default)'}`",
    ]
    if sess:
        props = ", ".join(f"{n} {s}" for s, n in (sess.get("proposals") or {}).items()) or "none"
        lines.append(f"- session: {sess.get('messages', 0)} messages, proposals: {props}, "
                     f"context {sess.get('context', {}).get('percent', '?')}%")
    if page_errors:
        lines += ["", "### Page errors", "", "```", *[redact(e)[:300] for e in page_errors], "```"]
    if problems:
        lines += ["", "### Server warnings and errors", "", "```",
                  *[redact(f"{p['time']} {p['level']} {p['logger']}: {p['message']}")[:400] for p in problems], "```"]
    lines += ["", "_A full diagnostics report was saved locally; attach it only if it contains nothing private._"]
    body = "\n".join(lines)
    url = issue_url(title, body)
    while len(url) > MAX_ISSUE_URL and len(body) > 500:  # keep it under GitHub's prefill limit
        body = body[: int(len(body) * 0.8)] + "\n\n_(truncated)_"
        url = issue_url(title, body)
    return body


def issue_url(title: str, body: str, repo: str = ISSUES_REPO) -> str:
    return f"https://github.com/{repo}/issues/new?" + urllib.parse.urlencode({"title": title, "body": body})


def environment(version: str, stale: bool) -> dict:
    return {"version": version, "stale": stale, "os": f"{platform.system()} {platform.release()} "
            f"({platform.machine()})", "python": platform.python_version(), "executable": redact(sys.executable)}


def dumps(report: dict) -> str:
    return json.dumps(report, indent=1, default=str)
