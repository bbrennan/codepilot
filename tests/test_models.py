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


def test_probe_counts_only_answers_from_the_model():
    busy = ClientError({"Error": {"Code": "ThrottlingException", "Message": "Too many requests"},
                        "ResponseMetadata": {"HTTPStatusCode": 429}}, "Converse")
    assert models._probe_error(busy)[0] is True
    # Not an answer from the model, so not "available" (these used to slip through and fill the picker).
    assert models._probe_error(ConnectionError("Could not connect to the endpoint URL"))[0] is False
    expired = ClientError({"Error": {"Code": "ExpiredTokenException", "Message": "The security token expired"},
                           "ResponseMetadata": {"HTTPStatusCode": 400}}, "Converse")
    assert models._probe_error(expired)[0] is False


def test_newest_in_family_wins_and_duplicates_are_marked(cfg):
    cfg = replace(cfg, provider="bedrock", region="us-east-1",
                  models={"fast": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                          "main": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                          "hard": "us.anthropic.claude-opus-4-5-20251101-v1:0"})
    have = ["us.anthropic.claude-sonnet-4-5-20250929-v1:0", "us.anthropic.claude-sonnet-4-6",
            "global.anthropic.claude-sonnet-4-6", "us.anthropic.claude-opus-4-5-20251101-v1:0",
            "global.anthropic.claude-opus-4-6-v1", "us.anthropic.claude-haiku-4-5-20251001-v1:0"]
    candidates = have + ["anthropic.claude-sonnet-5-5", "anthropic.claude-opus-5-5"]
    data = models.discover(cfg, refresh=True, lister=lambda c: candidates,
                           probe=lambda c, m: (m in have, "ok" if m in have else "You don't have access"))
    tiers = data["tiers"]
    assert tiers["main"] == {"model": "us.anthropic.claude-sonnet-4-6", "configured": cfg.models["main"],
                             "fallback": False, "upgraded": True}  # same geography as configured
    assert tiers["hard"]["model"] == "global.anthropic.claude-opus-4-6-v1" and tiers["hard"]["upgraded"]
    assert tiers["fast"]["model"] == cfg.models["fast"] and not tiers["fast"].get("upgraded")
    by_id = {m["id"]: m for m in data["models"]}
    assert by_id["global.anthropic.claude-sonnet-4-6"]["same_as"] == "us.anthropic.claude-sonnet-4-6"
    assert by_id["us.anthropic.claude-sonnet-4-6"]["newest"] and not by_id[cfg.models["main"]].get("newest")
    assert [m["id"] for m in data["models"] if m["available"] and "same_as" not in m][:2] == [
        "global.anthropic.claude-opus-4-6-v1", "us.anthropic.claude-opus-4-5-20251101-v1:0"]  # Opus first, newest first
    pinned = models.resolve_tiers(replace(cfg, latest_models=False), data)
    assert pinned["main"]["model"] == cfg.models["main"]


def test_known_profiles_are_probed_when_listing_is_denied(cfg, monkeypatch):
    class Denied:
        def list_inference_profiles(self, **kw):
            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "not authorized"}},
                              "ListInferenceProfiles")
    monkeypatch.setattr("codepilot.bedrock.make_client", lambda c, service: Denied())
    ids = models.bedrock_candidates(replace(cfg, provider="bedrock", region="us-west-2"))
    assert "us.anthropic.claude-sonnet-4-6" in ids and "global.anthropic.claude-opus-4-6-v1" in ids
    assert not any(i.startswith("eu.") for i in ids)


def test_a_run_where_nothing_answers_is_not_cached(cfg):
    cfg = bedrock_cfg(cfg)
    models.discover(cfg, refresh=True, lister=lambda c: CANDIDATES, probe=lambda c, m: (False, "token expired"))
    assert not (cfg.home / "models.json").exists()


def test_a_model_that_rejects_the_probe_parameters_is_available_not_denied():
    for msg in ("Unsupported parameter: temperature is not allowed with this model", "unsupported value for max_tokens"):
        err = ClientError({"Error": {"Code": "ValidationException", "Message": msg},
                           "ResponseMetadata": {"HTTPStatusCode": 400}}, "Converse")
        assert models._probe_error(err)[0] is True, msg
    gone = ClientError({"Error": {"Code": "ValidationException", "Message": "The provided model identifier is invalid."},
                        "ResponseMetadata": {"HTTPStatusCode": 400}}, "Converse")
    assert models._probe_error(gone)[0] is False


def test_a_messages_api_400_about_max_tokens_is_available_not_a_credentials_error():
    """The Anthropic SDK's errors carry status_code but no botocore code; 'token' inside 'max_tokens' once matched
    the credentials pattern and marked the model unavailable."""
    class SdkError(Exception):
        status_code = 400

    assert models._probe_error(SdkError("Error code: 400 - unsupported value for max_tokens"))[0] is True
    assert models._probe_error(SdkError("Error code: 400 - max_tokens: must be at least 16"))[0] is True
    assert models._probe_error(SdkError("Error code: 400 - The security token included in the request is expired"))[0] is False
