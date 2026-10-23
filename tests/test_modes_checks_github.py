import stat

import pytest

from codepilot import checks, github, modes, skills
from codepilot.agent import Agent
from codepilot.tools import build_tools
from fakes import FakeLLM, tool_use


def test_builtin_and_custom_modes(repo, cfg):
    names = [m.name for m in modes.all_modes(repo, cfg.home)]
    assert names == ["ask", "plan", "build", "debug", "bughunt", "spec", "review"]
    assert modes.get("act", repo, cfg.home).name == "build"  # old sessions keep working
    assert modes.get(None, repo, cfg.home).name == "build"
    assert "propose_edit" in modes.get("bughunt", repo, cfg.home).blocked
    custom = repo / ".codepilot" / "modes"
    custom.mkdir(parents=True)
    (custom / "perf.md").write_text("---\nname: perf\nlabel: Perf\ndescription: speed\ntier: hard  # big model\n"
                                    "blocked: run_command, propose_edit\nskills: diagnose-bug\n---\nMeasure first.\n")
    perf = modes.get("perf", repo, cfg.home)
    assert (perf.label, perf.tier, perf.builtin) == ("Perf", "hard", False)
    assert perf.blocked == {"run_command", "propose_edit"}
    text = modes.system_text(perf, repo, cfg.home)
    assert text.startswith("Measure first.") and "Disabled in this mode: propose_edit, run_command." in text
    assert '<skill name="diagnose-bug">' in text


def test_mode_tier_override_and_blocking(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "run_command", command="ls")], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, mode="ask")
    events = list(agent.chat(sess.id, "what is this"))
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] and "disabled in Ask mode" in result["output"]
    custom = repo / ".codepilot" / "modes"
    custom.mkdir(parents=True)
    (custom / "deep.md").write_text("---\nname: deep\ntier: hard\n---\nThink hard.\n")
    store.update_session(sess.id, mode="deep")
    llm.script.append([{"text": "deep answer"}])
    list(agent.chat(sess.id, "again"))
    assert llm.calls[-1]["model"] == cfg.models["hard"]


@pytest.mark.parametrize("args,kind", [
    ("pr view 12 --json title", "read"), ("pr diff 3", "read"), ("run view 99 --log-failed", "read"),
    ("search code foo -R org/repo", "read"), ("api repos/o/r/pulls", "read"), ("api -X GET repos/o/r", "read"),
    ("pr comment 3 --body hi", "write"), ("issue create --title t", "write"), ("api -X POST repos/o/r/issues", "write"),
    ("api repos/o/r/issues -f title=x", "write"), ("api --method=DELETE repos/o/r", "write"),
    ("auth token", None), ("secret list", None), ("repo delete o/r", None), ("pr merge 3", None), ("", None),
])
def test_github_classify(args, kind):
    assert github.classify(args.split()) == kind


def test_github_tool_approval_rules(cfg, monkeypatch):
    monkeypatch.setattr(github, "available", lambda: True)
    tool = {t.name: t for t in build_tools(cfg)}["github"]
    assert not tool.requires_approval({"args": "pr view 1"}, False)
    assert tool.requires_approval({"args": "gh pr comment 1 --body x"}, True)  # auto-run doesn't cover writes


def test_explore_cannot_make_approval_calls(cfg, store, repo, monkeypatch):
    monkeypatch.setattr(github, "available", lambda: True)
    ran = []
    monkeypatch.setattr(github, "run", lambda *a, **k: ran.append(a) or (0, "{}"))
    llm = FakeLLM([
        [tool_use("m1", "explore", task="look around")],
        [tool_use("s1", "github", args="pr comment 1 --body spam"), tool_use("s2", "github", args="pr view 1")],
        [{"text": "report"}],
        [{"text": "done"}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "go"))
    sub_results = llm.calls[2]["messages"][-1]["content"]
    assert sub_results[0]["toolResult"]["status"] == "error"
    assert len(ran) == 1 and "pr view 1" in ran[0][1]


def _fake_bin(dirpath, name, script):
    path = dirpath / name
    path.write_text("#!/bin/sh\n" + script + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_checks_detect_and_run(repo, tmp_path, monkeypatch):
    (repo / "pyproject.toml").write_text("[tool.mypy]\nstrict = true\n")
    venv_bin = repo / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    _fake_bin(venv_bin, "ruff", 'echo "agent/core.py:2:5: F841 unused"; exit 1')
    _fake_bin(venv_bin, "mypy", 'echo "Success: no issues found"; exit 0')
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    found = [(c.name, c.kind) for c in checks.detect(repo)]
    assert found == [("ruff", "lint"), ("mypy", "types")]
    out = checks.run_all(repo)
    assert "== ruff (lint) exit 1 ==\nagent/core.py:2:5: F841 unused" in out
    assert "== mypy (types) clean ==" in out
    assert checks.run_all(repo, "security").startswith("No analysers found")


def test_quick_check_is_syntax_only(repo, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    (repo / "bad.py").write_text("def f(:\n    pass\n")
    (repo / "boom.py").write_text("import os\nos.system('touch /tmp/should-not-run')\n")
    (repo / "c.json").write_text("{bad json}")
    assert "bad.py:1" in checks.quick_check(repo, "bad.py") and "syntax error" in checks.quick_check(repo, "bad.py")
    assert checks.quick_check(repo, "boom.py") == ""  # compiled, never executed
    assert "invalid json" in checks.quick_check(repo, "c.json")


def test_kiro_steering_and_global_agents(repo, cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(skills.Path, "home", lambda: tmp_path / "fakehome")
    steering = tmp_path / "fakehome" / ".kiro" / "steering"
    steering.mkdir(parents=True)
    (steering / "always.md").write_text("---\ninclusion: always\n---\nUse type hints.")
    (steering / "manual.md").write_text("---\ninclusion: manual\n---\nOnly when asked.")
    (steering / "plain.md").write_text("Prefer small PRs.")
    cfg.home.mkdir(parents=True, exist_ok=True)
    (cfg.home / "AGENTS.md").write_text("Global rule.")
    text = skills.project_instructions(repo, cfg.home)
    assert "Global rule." in text and "Use type hints." in text and "Prefer small PRs." in text
    assert "Only when asked." not in text
