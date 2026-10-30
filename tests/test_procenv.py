"""Commands codepilot runs never wait for a human: no editors, prompts or pagers, and a timeout ends everything."""

import subprocess
import time

import pytest

from codepilot import procenv
from codepilot.tools import ToolContext, ToolError, _run_command


@pytest.fixture
def ctx(repo, cfg, store):
    return ToolContext(root=repo.resolve(), cfg=cfg, store=store, session_id=store.create_session(str(repo), "x").id)


def test_the_environment_turns_off_editors_prompts_and_pagers(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/.venv")
    monkeypatch.setenv("EDITOR", "vim")
    env = procenv.env()
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_EDITOR"] == ":" and env["GIT_SEQUENCE_EDITOR"] == ":"
    assert env["GIT_PAGER"] == env["PAGER"] == env["GH_PAGER"] == "cat"
    assert env["GH_PROMPT_DISABLED"] == "1" and env["GCM_INTERACTIVE"] == "never"
    assert "VIRTUAL_ENV" not in env and env["EDITOR"] == "vim"  # git uses GIT_EDITOR first; the rest is untouched


def test_a_commit_without_a_message_fails_fast_instead_of_opening_an_editor(ctx, repo, monkeypatch):
    for var in ("GIT_EDITOR", "GIT_SEQUENCE_EDITOR"):  # as on a normal machine (some shells set these)
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EDITOR", "sleep 60")  # like `code --wait` or vim on a real machine
    monkeypatch.setenv("VISUAL", "sleep 60")
    monkeypatch.setenv("TERM", "xterm-256color")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    started = time.monotonic()
    out = _run_command(ctx, "git commit", 30, "command")
    assert time.monotonic() - started < 10
    assert "exit code 1" in out and "empty commit message" in out.lower()


def test_a_timeout_ends_the_whole_process_tree(ctx, tmp_path):
    import os
    pidfile = tmp_path / "child.pid"
    with pytest.raises(ToolError, match="timed out after 2s"):
        _run_command(ctx, f"sleep 60 & echo $! > {pidfile}; wait", 2, "command")
    child = int(pidfile.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:  # killed processes are reaped asynchronously
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(child, 9)
    raise AssertionError("the command's background child outlived the timeout")


def test_commands_get_no_stdin(ctx):
    started = time.monotonic()
    out = _run_command(ctx, "cat", 10, "command")  # would wait for input if it inherited a terminal
    assert out.startswith("$ cat\nexit code 0") and time.monotonic() - started < 5


def test_a_timeout_returns_even_if_a_child_escaped_the_process_group(ctx, tmp_path):
    import os
    import sys
    pidfile = tmp_path / "escaped.pid"
    script = f"import os, time; os.setsid(); open({str(pidfile)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    started = time.monotonic()
    try:
        with pytest.raises(ToolError, match="timed out"):
            _run_command(ctx, f"{sys.executable} -c \"{script}\" & wait", 2, "command")
        assert time.monotonic() - started < 10  # not stuck waiting for the escaped child's pipes
    finally:
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), 9)
            except ProcessLookupError:
                pass
