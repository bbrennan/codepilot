"""Problem reports: what's collected, what's redacted, and what (little) goes into a public GitHub issue."""

import json
import logging
from pathlib import Path

import pytest
from fakes import FakeLLM
from starlette.testclient import TestClient

from codepilot import diagnostics
from codepilot.agent import Agent
from codepilot.server import create_app

H = {"X-Codepilot": "1"}


@pytest.mark.parametrize("raw,gone", [
    ("key AKIAIOSFODNN7EXAMPLE here", "AKIAIOSFODNN7EXAMPLE"),
    ("password=hunter2!", "hunter2"),
    ("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG", "wJalrXUtnFEMI"),
    ("using sk-ant-api03-abcdefghijklmnop", "sk-ant-api03"),
    ("openai sk-proj-abcdefghijklmnopqrstuvwx", "sk-proj-abcdefgh"),
    ("gh token ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_abcdef"),
    ("Authorization: Bearer abc.def.ghijklmnopqrstu", "abc.def.ghijk"),
    ("https://user:s3cret@proxy.corp:8080/", "s3cret"),
    ("mail jane.doe@example.com now", "jane.doe@example.com"),
])
def test_redact(raw, gone):
    assert gone not in diagnostics.redact(raw)


def test_redact_home_and_extra_secrets():
    text = f"{Path.home()}/code/app.py with token-value-123456"
    out = diagnostics.redact(text, ("token-value-123456",))
    assert str(Path.home()) not in out and out.startswith("~/code/app.py") and "token-value" not in out


def test_report_and_issue(cfg, store, repo, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secretsecretsecret999")
    agent = Agent(cfg, store, llm=FakeLLM([[{"text": "The PURPLE-ELEPHANT plan, key AKIAIOSFODNN7EXAMPLE"}]]))
    client = TestClient(create_app(cfg, store, agent))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    list(agent.chat(sid, "tell me the plan; my key is sk-ant-secretsecretsecret999"))
    logging.getLogger("codepilot.test").warning("disk quota nearly full in %s", Path.home())

    body = {"sid": sid, "title": "Plan looks wrong", "description": "It said odd things. password=hunter2",
            "include_transcript": True, "client": {"browser": "Chrome", "errors": ["TypeError: x is undefined"]}}
    r = client.post("/api/report", json=body, headers=H).json()
    dumped = json.dumps(r)
    assert "sk-ant-secretsecretsecret999" not in dumped and "AKIAIOSFODNN7EXAMPLE" not in dumped
    assert "hunter2" not in dumped and str(Path.home()) not in dumped

    report = r["report"]
    assert report["environment"]["version"] and report["settings"]["provider"] == "bedrock"
    assert report["session"]["messages"] == 2 and "PURPLE-ELEPHANT" in json.dumps(report["events"])
    assert any("disk quota" in p["message"] for p in report["server_problems"])

    issue = r["issue_body"]
    assert "PURPLE-ELEPHANT" not in issue and "tell me the plan" not in issue  # no conversation in the issue
    assert "It said odd things" in issue and "TypeError: x is undefined" in issue and "disk quota" in issue
    assert r["issue_url"].startswith("https://github.com/bbrennan/codepilot/issues/new?")
    assert r["filename"].startswith("codepilot-report-") and r["filename"].endswith(".json")

    no_transcript = client.post("/api/report", json={**body, "include_transcript": False}, headers=H).json()
    assert "events" not in no_transcript["report"]


def test_issue_url_stays_under_githubs_limit(cfg, store):
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    r = client.post("/api/report", json={"title": "Long", "description": "x " * 20_000}, headers=H).json()
    assert len(r["issue_url"]) <= diagnostics.MAX_ISSUE_URL and "(truncated)" in r["issue_body"]


def test_report_needs_the_csrf_header(cfg, store):
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    assert client.post("/api/report", json={}).status_code == 403
