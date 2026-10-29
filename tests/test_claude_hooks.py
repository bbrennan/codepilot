"""The Claude Code hooks in .claude/hooks enforce CLAUDE.md mechanically: exit 2 blocks the action."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def run(hook, payload):
    return subprocess.run([sys.executable, str(HOOKS / hook)], input=json.dumps(payload), text=True,
                          capture_output=True, timeout=60)


def git_repo(tmp_path, branch):
    for cmd in (["init", "-q", "-b", branch], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    return tmp_path


def bash(cwd, command):
    return {"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": command}}


@pytest.mark.parametrize("branch", ["main", "develop"])
@pytest.mark.parametrize("command", ["git commit -m x", "git push", "git push origin HEAD", "git add a && git commit -m x"])
def test_commits_and_pushes_are_blocked_on_protected_branches(tmp_path, branch, command):
    r = run("guard_git.py", bash(git_repo(tmp_path, branch), command))
    assert r.returncode == 2 and branch in r.stderr


@pytest.mark.parametrize("command", ["git commit -m x", "git push -u origin fix/a", "git status", "git log --oneline"])
def test_work_branches_are_allowed(tmp_path, command):
    assert run("guard_git.py", bash(git_repo(tmp_path, "fix/a"), command)).returncode == 0


@pytest.mark.parametrize("command", ["git push --force origin fix/a", "git push -f", "git push origin +fix/a",
                                     "git commit --no-verify -m x", "git push origin HEAD:main",
                                     "git push origin fix/a:develop"])
def test_force_no_verify_and_pushes_to_protected_refs_are_blocked_anywhere(tmp_path, command):
    assert run("guard_git.py", bash(git_repo(tmp_path, "fix/a"), command)).returncode == 2


def test_non_git_commands_and_other_tools_pass(tmp_path):
    repo = git_repo(tmp_path, "main")
    assert run("guard_git.py", bash(repo, "make test")).returncode == 0
    assert run("guard_git.py", {"tool_name": "Read", "cwd": str(repo), "tool_input": {"file_path": "x"}}).returncode == 0


def edit(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_a_javascript_syntax_error_in_app_js_is_reported(tmp_path):
    static = tmp_path / "codepilot" / "static"
    static.mkdir(parents=True)
    (static / "app.js").write_text("function (){")
    r = run("check_edit.py", edit(static / "app.js"))
    assert r.returncode == 2 and "app.js" in r.stderr
    (static / "app.js").write_text("function f() {}")
    assert run("check_edit.py", edit(static / "app.js")).returncode == 0


@pytest.mark.skipif(not (shutil.which("ruff") or shutil.which("uvx")), reason="ruff not available")
def test_a_python_lint_error_is_reported(tmp_path):
    bad, good = tmp_path / "bad.py", tmp_path / "good.py"
    bad.write_text("import os\n")
    good.write_text("x = 1\n")
    assert run("check_edit.py", edit(bad)).returncode == 2
    assert run("check_edit.py", edit(good)).returncode == 0


def test_other_files_and_missing_paths_are_ignored(tmp_path):
    (tmp_path / "notes.md").write_text("# hi")
    assert run("check_edit.py", edit(tmp_path / "notes.md")).returncode == 0
    assert run("check_edit.py", edit(tmp_path / "gone.py")).returncode == 0
    assert run("check_edit.py", {"tool_name": "Edit", "tool_input": {}}).returncode == 0
