from dataclasses import replace

from botocore.exceptions import ClientError
from fakes import FakeLLM
from starlette.testclient import TestClient

from codepilot import models
from codepilot.agent import Agent
from codepilot.server import create_app

CANDIDATES = ["anthropic.claude-opus-5-5", "anthropic.claude-sonnet-5-5", "anthropic.claude-haiku-5-5",
              "anthropic.claude-haiku-4-5", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"]


def fake_probe(calls):
    def probe(cfg, model):
        calls.append(model)
        if model == "anthropic.claude-haiku-5-5":
            return False, "Model access is pending onboarding for this account"
        return True, "ok"
    return probe


def bedrock_cfg(cfg):
    return replace(cfg, provider="bedrock", bedrock_api="auto",
                   models={"fast": "anthropic.claude-haiku-5-5", "main": "anthropic.claude-sonnet-5-5",
                           "hard": "anthropic.claude-opus-5-5"})


def test_discover_probes_caches_and_falls_back(cfg):
    cfg = bedrock_cfg(cfg)
    calls = []
    data = models.discover(cfg, refresh=True, probe=fake_probe(calls), lister=lambda c: list(CANDIDATES))
    avail = [m["id"] for m in data["models"] if m["available"]]
    assert "anthropic.claude-haiku-5-5" not in avail and len(avail) == 4
    off = next(m for m in data["models"] if not m["available"])
    assert off["reason"].startswith("Model access is pending")
    assert data["tiers"]["fast"] == {"model": "anthropic.claude-haiku-4-5", "configured": "anthropic.claude-haiku-5-5",
                                     "fallback": True, "reason": off["reason"]}
    assert data["tiers"]["main"]["model"] == "anthropic.claude-sonnet-5-5" and not data["tiers"]["main"]["fallback"]
    assert {m["id"]: m["api"] for m in data["models"]}["us.anthropic.claude-sonnet-4-5-20250929-v1:0"] == "Converse"
    # Cached: no new probes until refresh.
    again = models.discover(cfg, probe=fake_probe(calls), lister=lambda c: list(CANDIDATES))
    assert again["checked_at"] == data["checked_at"] and len(calls) == len(CANDIDATES)


def test_probe_error_classification():
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "You don't have access to the model"},
                          "ResponseMetadata": {"HTTPStatusCode": 403}}, "Converse")
    assert models._probe_error(denied)[0] is False
    other = ClientError({"Error": {"Code": "ValidationException", "Message": "maxTokens is too small for thinking"},
                         "ResponseMetadata": {"HTTPStatusCode": 400}}, "Converse")
    assert models._probe_error(other)[0] is True


def test_labels():
    assert models.label("anthropic.claude-opus-5-5") == "Claude Opus 5.5"
    assert models.label("us.anthropic.claude-sonnet-4-5-20250929-v1:0") == "Claude Sonnet 4.5"
    assert models.label("anthropic.claude-opus-5") == "Claude Opus 5"
    assert models.label("llama3.2:3b") == "llama3.2:3b"


def test_agent_uses_fallback_and_session_override(cfg, store, repo):
    cfg = bedrock_cfg(cfg)
    models.discover(cfg, refresh=True, probe=fake_probe([]), lister=lambda c: list(CANDIDATES))
    llm = FakeLLM([[{"text": "a"}], [{"text": "b"}]])
    agent = Agent(cfg, store, llm=llm)
    assert agent.tier_model("fast") == "anthropic.claude-haiku-4-5"
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "hi"))
    assert llm.calls[-1]["model"] == "anthropic.claude-sonnet-5-5"
    store.update_session(sess.id, model="us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    list(agent.chat(sess.id, "again"))
    assert llm.calls[-1]["model"] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


def test_models_endpoint_and_model_patch(cfg, store, repo, monkeypatch):
    cfg = bedrock_cfg(cfg)
    monkeypatch.setattr(models, "probe_bedrock", fake_probe([]))
    monkeypatch.setattr(models, "bedrock_candidates", lambda c: list(CANDIDATES))
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    H = {"X-Codepilot": "1"}
    data = client.get("/api/models", params={"refresh": "1"}).json()
    assert data["tiers"]["fast"]["fallback"] is True
    sess = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()
    out = client.patch(f"/api/sessions/{sess['id']}", json={"model": "anthropic.claude-opus-5-5"}, headers=H).json()
    assert out["session"]["model"] == "anthropic.claude-opus-5-5"
    assert out["context"]["window"] == 1_000_000
