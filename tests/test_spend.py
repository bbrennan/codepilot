"""What this has cost: per session, per turn and today, and the optional daily cap."""

from dataclasses import replace
from datetime import datetime

from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot.agent import Agent
from codepilot.server import create_app
from codepilot.spend import Spend


def usage(input=0, output=0):
    return {"inputTokens": input, "outputTokens": output}


def priced(cfg):
    cfg.home.mkdir(parents=True, exist_ok=True)
    (cfg.home / "prices.toml").write_text('["claude-sonnet-5-5"]\ninput = 2.0\noutput = 10.0\n')
    return cfg


SONNET = "anthropic.claude-sonnet-5-5"


def test_a_session_and_today_are_priced(cfg, store, repo):
    spend = Spend(priced(cfg), store)
    one = store.create_session(str(repo), "main").id
    two = store.create_session(str(repo), "main").id
    store.add_usage(one, SONNET, usage(input=1_000_000))
    store.add_usage(two, SONNET, usage(output=1_000_000))
    view = spend.view(one)
    assert view["cost"]["total"] == 2.0 and view["by_model"][0]["cost"] == 2.0
    assert view["today"]["total"] == 12.0  # every session
    assert view["prices"]["loaded"] and view["prices"]["path"].endswith("prices.toml")


def test_usage_from_before_today_doesnt_count_as_today(cfg, store, repo):
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    assert Spend(priced(cfg), store).view(sid)["today"]["total"] == 2.0
    tomorrow = datetime(2099, 1, 1, 12, 0)
    assert Spend(priced(cfg), store, today=lambda: tomorrow).view(sid)["today"]["total"] == 0


def test_without_prices_nothing_is_priced_but_nothing_breaks(cfg, store, repo):
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, SONNET, usage(input=5))
    view = Spend(cfg, store).view(sid)
    assert not view["prices"]["loaded"] and view["cost"]["unpriced"] == [SONNET] and view["by_model"][0]["cost"] is None


def test_a_broken_prices_file_is_reported(cfg, store, repo):
    cfg.home.mkdir(parents=True, exist_ok=True)
    (cfg.home / "prices.toml").write_text("[oops\n")
    view = Spend(cfg, store).view(store.create_session(str(repo), "main").id)
    assert "prices.toml" in view["prices"]["error"] and not view["prices"]["loaded"]


def test_a_custom_prices_path(cfg, store, repo, tmp_path):
    other = tmp_path / "mine.toml"
    other.write_text('["claude-sonnet-5-5"]\ninput = 4.0\n')
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    assert Spend(replace(cfg, prices_path=str(other)), store).view(sid)["cost"]["total"] == 4.0


def test_local_models_are_free(cfg, store, repo):
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, "llama3.2:3b", usage(input=1_000_000))
    view = Spend(replace(cfg, provider="ollama"), store).view(sid)
    assert view["cost"]["total"] == 0 and view["cost"]["unpriced"] == [] and view["by_model"][0]["cost"] == 0


def test_one_call_is_priced(cfg, store):
    spend = Spend(priced(cfg), store)
    assert spend.call(SONNET, {"inputTokens": 1000, "outputTokens": 100, "cacheReadInputTokens": 0}) == 0.003
    assert spend.call("gpt-9", {"inputTokens": 1}) is None


def test_usage_goes_to_the_turn_it_happened_in(cfg, store, repo):
    spend = Spend(priced(cfg), store)
    sid = store.create_session(str(repo), "main").id
    first = store.add_message(sid, "user", [{"text": "Implement task 1 of spec x: a"}])
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    store.add_message(sid, "assistant", [{"text": "ok"}])
    store.add_message(sid, "user", [{"toolResult": {"toolUseId": "t", "content": []}}])  # part of the same turn
    store.add_usage(sid, SONNET, usage(output=100_000))
    second = store.add_message(sid, "user", [{"text": "Implement task 2 of spec x: b"}])
    store.add_usage(sid, SONNET, usage(input=500_000))
    assert spend.turns(sid) == [{"mid": first, "text": "Implement task 1 of spec x: a", "cost": 3.0},
                                {"mid": second, "text": "Implement task 2 of spec x: b", "cost": 1.0}]


def test_a_turn_with_unpriced_usage_has_no_cost(cfg, store, repo):
    spend = Spend(priced(cfg), store)
    sid = store.create_session(str(repo), "main").id
    store.add_message(sid, "user", [{"text": "go"}])
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    store.add_usage(sid, "gpt-9", usage(input=1))
    assert spend.turns(sid)[0]["cost"] is None


# -- the daily cap ------------------------------------------------------------------------------------------------

def capped(cfg, store, limit=10.0, today=None):
    kw = {"today": today} if today else {}
    return Spend(replace(priced(cfg), daily_budget=limit), store, **kw)


def spent(store, repo, dollars):
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, SONNET, usage(input=int(dollars * 500_000)))


def test_no_budget_means_no_checks(cfg, store, repo):
    spent(store, repo, 1000)
    assert Spend(priced(cfg), store).check() == "ok"


def test_the_cap_warns_once_at_80_percent_then_stops(cfg, store, repo):
    spend = capped(cfg, store)
    assert spend.check() == "ok"
    spent(store, repo, 8)
    assert spend.check() == "warn"
    assert spend.check() == "ok"  # once
    spent(store, repo, 2)
    assert spend.check() == "stop" and spend.check() == "stop"


def test_continue_anyway_lasts_until_midnight(cfg, store, repo):
    now = {"t": datetime(2026, 10, 31, 23, 0)}
    spend = capped(cfg, store, today=lambda: now["t"])
    sid = store.create_session(str(repo), "main").id
    store._db.execute("INSERT INTO usage (session_id, model, input_tokens, created) VALUES (?, ?, ?, ?)",
                      (sid, SONNET, 10_000_000, datetime(2026, 10, 31, 22, 0).timestamp()))
    assert spend.check() == "stop"
    spend.override_today()
    assert spend.check() == "ok"
    assert capped(cfg, store, today=lambda: now["t"]).check() == "ok"  # survives a restart
    now["t"] = datetime(2026, 11, 1, 0, 1)
    store._db.execute("INSERT INTO usage (session_id, model, input_tokens, created) VALUES (?, ?, ?, ?)",
                      (sid, SONNET, 10_000_000, datetime(2026, 11, 1, 0, 0, 30).timestamp()))
    assert spend.check() == "stop"  # a new day


def test_unpriced_usage_doesnt_count_towards_the_cap_and_is_named(cfg, store, repo):
    spend = capped(cfg, store)
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, "gpt-9", usage(input=10**9))
    assert spend.check() == "ok" and spend.view(sid)["today"]["unpriced"] == ["gpt-9"]


# -- in the agent and the API -------------------------------------------------------------------------------------

def price_all(cfg):
    """A price for whatever model the session uses, so FakeLLM's token counts cost something."""
    cfg.home.mkdir(parents=True, exist_ok=True)
    (cfg.home / "prices.toml").write_text("".join(f'["{m}"]\ninput = 1000000.0\noutput = 1000000.0\n'
                                                  for m in set(cfg.models.values())))
    return cfg


def test_each_model_call_reports_its_cost(cfg, store, repo):
    agent = Agent(price_all(cfg), store, llm=FakeLLM([[{"text": "hi"}]]))
    sess = store.create_session(str(repo), "main")
    event = next(e for e in agent.chat(sess.id, "hello") if e["type"] == "usage")
    assert event["cost"] > 0


def test_a_turn_stops_before_the_next_model_call_at_the_cap(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "read_file", path="agent/core.py")], [{"text": "never sent"}]])
    agent = Agent(replace(price_all(cfg), daily_budget=0.01), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "read it"))
    budget = next(e for e in events if e["type"] == "budget")
    assert budget["limit"] == 0.01 and budget["spent"] >= 0.01
    assert len(llm.calls) == 1 and events[-1]["type"] == "done"


def test_the_next_message_is_held_at_the_cap_and_runs_after_continuing(cfg, store, repo):
    llm = FakeLLM([[{"text": "one"}], [{"text": "two"}]])
    agent = Agent(replace(price_all(cfg), daily_budget=0.01), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "first"))
    assert any(e["type"] == "budget" for e in agent.chat(sess.id, "second")) and len(llm.calls) == 1
    agent.spend.override_today()
    list(agent.chat(sess.id, "third"))
    assert len(llm.calls) == 2  # the held message and this one reach the model together
    roles = [m["role"] for m in llm.calls[-1]["messages"]]
    assert roles == ["user", "assistant", "user"]


def test_nearing_the_cap_warns_once(cfg, store, repo):
    llm = FakeLLM([[{"text": "one"}], [{"text": "two"}], [{"text": "three"}]])
    agent = Agent(replace(price_all(cfg), daily_budget=1_000_000.0), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "first"))
    store.add_usage(sess.id, cfg.models["main"], {"inputTokens": 900_000})
    assert any(e["type"] == "notice" and "daily budget" in e["message"] for e in agent.chat(sess.id, "second"))
    assert not any(e["type"] == "notice" for e in agent.chat(sess.id, "third"))


def test_explore_stops_at_the_cap_too(cfg, store, repo):
    llm = FakeLLM([[tool_use("e1", "explore", task="look")], [tool_use("r1", "read_file", path="agent/core.py")],
                   [{"text": "never sent"}]])
    agent = Agent(replace(price_all(cfg), daily_budget=1e-9), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    agent.spend.override_today()
    agent.spend.check = lambda: "stop" if len(llm.calls) >= 2 else "ok"
    list(agent.chat(sess.id, "explore"))
    assert len(llm.calls) == 2


def test_the_api_reports_cost_turns_and_takes_an_override(cfg, store, repo):
    agent = Agent(replace(price_all(cfg), daily_budget=0.01), store, llm=FakeLLM([[{"text": "one"}]]))
    client = TestClient(create_app(agent.cfg, store, agent))
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "Implement task 1 of spec x: a"))
    body = client.get(f"/api/sessions/{sess.id}/usage").json()
    assert body["cost"]["total"] > 0 and body["today"]["total"] > 0 and body["by_model"][0]["cost"] > 0
    assert body["budget"] == {"limit": 0.01, "overridden": False} and body["prices"]["loaded"]
    assert client.get(f"/api/sessions/{sess.id}").json()["usage"]["cost"]["total"] > 0
    turns = client.get(f"/api/sessions/{sess.id}/turn-costs").json()["turns"]
    assert turns[0]["text"].startswith("Implement task 1") and turns[0]["cost"] > 0
    assert client.post("/api/budget/override", headers={"X-Codepilot": "1"}).status_code == 200
    assert client.get(f"/api/sessions/{sess.id}/usage").json()["budget"]["overridden"] is True
