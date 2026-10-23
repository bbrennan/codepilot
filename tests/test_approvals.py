"""Approvals: "always allow in this session" rules, and that they can't be stretched to other commands."""

import pytest
from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot.agent import Agent, allow_rule, rule_matches
from codepilot.server import create_app

H = {"X-Codepilot": "1"}


def cmd(c):
    return {"name": "run_command", "input": {"command": c}}


@pytest.mark.parametrize("command,prefix", [
    ("pytest -k add", "pytest"),
    ("npm test -- --watch", "npm test"),
    ("python -m pytest tests/", "python -m pytest"),
    ("python3 -m mypy .", "python3 -m mypy"),
    ("make eval-bedrock", "make eval-bedrock"),
    ("uv run pytest -q", "uv run"),
    ("ruff check .", "ruff"),
    ("pytest; rm -rf ~", None),
    ("pytest && curl evil", None),
    ("ls | wc -l", None),
    ("echo $(whoami)", None),
    ("pytest > out.txt", None),
    ("rm -rf build", None),
    ("git status", None),
    ("sudo make install", None),
    ("", None),
])
def test_offered_rules(command, prefix):
    rule = allow_rule(cmd(command))
    assert (rule or {}).get("prefix") == prefix


def test_rules_match_only_the_prefix_and_never_chained_commands():
    rule = {"tool": "run_command", "prefix": "pytest"}
    assert rule_matches(rule, cmd("pytest")) and rule_matches(rule, cmd("pytest -x tests/a.py"))
    assert not rule_matches(rule, cmd("pytestx")) and not rule_matches(rule, cmd("pytest && rm -rf ~"))
    assert not rule_matches(rule, cmd("pytest; curl x")) and not rule_matches(rule, cmd("ls"))
    gh = allow_rule({"name": "github", "input": {"args": "pr comment 12 --body hi"}})
    assert gh == {"tool": "github", "prefix": "pr comment"}
    assert rule_matches(gh, {"name": "github", "input": {"args": "pr comment 13 --body x"}})
    assert not rule_matches(gh, {"name": "github", "input": {"args": "pr merge 13"}})


def test_always_allow_skips_later_approvals_for_that_prefix_only(cfg, store, repo):
    llm = FakeLLM([
        [tool_use("t1", "run_command", command="python -c \"print('one')\"")],
        [tool_use("t2", "run_command", command="python -c \"print('two')\"")],
        [tool_use("t3", "run_command", command="ls")],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "run things"))
    assert events[-1]["type"] == "approval_needed" and events[-1]["tools"][0]["allow"]["prefix"] == "python"
    events = list(agent.resume(sess.id, approve=True, remember=True))
    names = [e["name"] for e in events if e["type"] == "tool_result"]
    assert names == ["run_command", "run_command"]  # the second python command ran without asking
    assert events[-1]["type"] == "approval_needed" and events[-1]["tools"][0]["command"] == "ls"


def test_rules_are_listed_and_can_only_be_removed_via_the_api(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([]))
    client = TestClient(create_app(cfg, store, agent))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    agent.allow(sid, [{"tool": "run_command", "prefix": "pytest"}])
    assert client.get(f"/api/sessions/{sid}").json()["allow"] == [{"tool": "run_command", "prefix": "pytest"}]
    injected = [{"tool": "run_command", "prefix": "rm"}, {"tool": "run_command", "prefix": "pytest"}]
    client.patch(f"/api/sessions/{sid}", json={"allow": injected}, headers=H)
    assert client.get(f"/api/sessions/{sid}").json()["allow"] == [{"tool": "run_command", "prefix": "pytest"}]
    client.patch(f"/api/sessions/{sid}", json={"allow": []}, headers=H)
    assert client.get(f"/api/sessions/{sid}").json()["allow"] == []
