"""What this has cost: per session, per turn and today, and the optional daily cap."""

from dataclasses import replace
from datetime import datetime

from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot.agent import Agent
from codepilot.server import create_app
from codepilot.spend import Spend
from codepilot.store import Store


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
    local = Spend(replace(cfg, provider="ollama"), store)
    local.record(sid, "llama3.2:3b", usage(input=1_000_000))
    view = local.view(sid)
    assert view["cost"]["total"] == 0 and view["cost"]["unpriced"] == [] and view["by_model"][0]["cost"] == 0


def test_switching_provider_doesnt_rewrite_what_earlier_calls_cost(cfg, store, repo):
    sid = store.create_session(str(repo), "main").id
    cloud = Spend(priced(cfg), store)
    local = Spend(replace(cfg, provider="ollama"), store)
    cloud.record(sid, SONNET, usage(input=1_000_000))
    local.record(sid, "llama3.2:3b", usage(input=1_000_000))
    for spend in (cloud, local):  # the provider in use now mustn't matter
        view = spend.view(sid)
        assert view["cost"]["total"] == 2.0 and view["cost"]["unpriced"] == [] and view["today"]["total"] == 2.0


def test_a_tilde_in_the_prices_path_means_home(cfg, store, repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "mine.toml").write_text('["claude-sonnet-5-5"]\ninput = 4.0\n')
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    assert Spend(replace(cfg, prices_path="~/mine.toml"), store).view(sid)["cost"]["total"] == 4.0


def test_a_turn_with_no_model_calls_has_no_cost_rather_than_zero(cfg, store, repo):
    spend = Spend(priced(cfg), store)
    sid = store.create_session(str(repo), "main").id
    store.add_message(sid, "user", [{"text": "Implement task 1 of spec x: held at the cap"}])
    assert spend.turns(sid)[0]["cost"] is None


def test_a_turn_that_resumes_after_tool_results_is_still_a_turn(cfg, store, repo):
    spend = Spend(priced(cfg), store)
    sid = store.create_session(str(repo), "main").id
    first = store.add_message(sid, "user", [{"text": "first"}])
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    second = store.add_message(sid, "user", [{"toolResult": {"toolUseId": "t", "content": []}}, {"text": "carry on"},
                                             {"text": "<turn_context>\nx\n</turn_context>"}])
    store.add_usage(sid, SONNET, usage(input=500_000))
    assert [(t["mid"], t["text"], t["cost"]) for t in spend.turns(sid)] == [(first, "first", 2.0),
                                                                            (second, "carry on", 1.0)]


def test_a_message_steered_in_mid_turn_doesnt_split_the_turn(cfg, store, repo):
    from codepilot.agent import QUEUED_PREFIX
    spend = Spend(priced(cfg), store)
    sid = store.create_session(str(repo), "main").id
    store.add_message(sid, "user", [{"text": "first"}])
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    store.add_message(sid, "user", [{"toolResult": {"toolUseId": "t", "content": []}},
                                    {"text": QUEUED_PREFIX + "use v2"}])
    store.add_usage(sid, SONNET, usage(input=500_000))
    assert [t["cost"] for t in spend.turns(sid)] == [3.0]


def test_a_rewound_turns_cost_stays_billed_but_leaves_the_estimates(cfg, store, repo):
    spend = Spend(priced(cfg), store)
    sid = store.create_session(str(repo), "main").id
    first = store.add_message(sid, "user", [{"text": "first"}])
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    second = store.add_message(sid, "user", [{"text": "second"}])
    store.add_usage(sid, SONNET, usage(input=5_000_000))
    store.delete_messages_from(sid, second)
    assert [(t["mid"], t["cost"]) for t in spend.turns(sid)] == [(first, 2.0)]  # not 12.0
    assert spend.view(sid)["cost"]["total"] == 12.0  # you still paid for it


def test_an_override_during_a_warning_isnt_lost(cfg, store, repo):
    import threading
    spend = capped(cfg, store)
    spent(store, repo, 8)
    real, fired = spend._state, []

    def state_then_override():
        state = real()
        if not fired:  # the override arrives just after the warning read the state
            fired.append(threading.Thread(target=spend.override_today))
            fired[0].start()
            fired[0].join(0.2)
        return state

    spend._state = state_then_override
    assert spend.check() == "warn"
    fired[0].join(2)
    spend._state = real
    assert spend.view(store.create_session(str(repo), "main").id)["budget"]["overridden"] is True


def test_a_failed_save_leaves_the_state_file_whole(cfg, store, monkeypatch):
    spend = capped(cfg, store)
    spend.override_today()
    before = (cfg.home / "budget.json").read_text()

    def fails(*_):
        raise OSError("disk full")

    monkeypatch.setattr("codepilot.spend.os.replace", fails)
    spend._save({"date": "2099-01-01"})
    assert (cfg.home / "budget.json").read_text() == before


def test_the_warning_and_the_cap_name_what_they_leave_out(cfg, store, repo):
    agent = Agent(replace(priced(cfg), daily_budget=10.0), store, llm=FakeLLM([[{"text": "one"}]]))
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, SONNET, usage(input=4_000_000))
    store.add_usage(sid, "mystery-model", usage(input=5))
    events = list(agent.chat(sid, "go"))
    assert any(e["type"] == "notice" and "mystery-model" in e["message"] for e in events)
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    assert [e["unpriced"] for e in agent.chat(sid, "again") if e["type"] == "budget"] == [["mystery-model"]]


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


def test_deleting_a_chat_doesnt_refund_it(cfg, store, repo):
    spend = capped(cfg, store)
    sid = store.create_session(str(repo), "main").id
    store.add_usage(sid, SONNET, usage(input=5_000_000))
    store.delete_session(sid)
    assert spend.spent_today() == 10.0 and spend.capped()


def test_an_existing_database_keeps_its_usage_and_stops_refunding_it(cfg, repo):
    old = Store(cfg.home)
    sid = old.create_session(str(repo), "main").id
    old.add_usage(sid, SONNET, usage(input=7), local=True)
    old._db.executescript("""
        ALTER TABLE usage RENAME TO usage_now;
        CREATE TABLE usage (id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read INTEGER NOT NULL DEFAULT 0, cache_write INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
        INSERT INTO usage (id, session_id, model, input_tokens, created)
            SELECT id, session_id, model, input_tokens, created FROM usage_now;
        DROP TABLE usage_now;
    """)
    old._db.close()
    store = Store(cfg.home)
    assert store.usage(sid)["by_model"][0]["input"] == 7
    store.delete_session(sid)
    assert [r["input"] for r in store.usage_since(0)] == [7]
    store._db.close()
    assert Store(cfg.home).usage_since(0)[0]["input"] == 7  # migrating twice changes nothing


def test_a_summary_isnt_started_at_the_cap(cfg, store, repo):
    agent = Agent(replace(priced(cfg), daily_budget=10.0), store, llm=FakeLLM([[{"text": "one"}]]))
    sid = store.create_session(str(repo), "main").id
    list(agent.chat(sid, "first"))
    before = len(store.live_messages(sid))
    store.add_usage(sid, SONNET, usage(input=5_000_000))
    assert list(agent.ctxm.summarize(sid, keep_turns=0)) == []
    assert not [c for c in agent.llm.calls if "complete" in c] and len(store.live_messages(sid)) == before


def test_a_new_task_after_steering_is_still_a_turn(cfg, store, repo):
    from codepilot.agent import QUEUED_PREFIX
    spend = Spend(priced(cfg), store)
    sid = store.create_session(str(repo), "main").id
    store.add_message(sid, "user", [{"text": "first"}])
    store.add_usage(sid, SONNET, usage(input=1_000_000))
    mid = store.add_message(sid, "user", [{"toolResult": {"toolUseId": "t", "content": []}},
                                          {"text": QUEUED_PREFIX + "use v2"}, {"text": "next task"}])
    store.add_usage(sid, SONNET, usage(input=500_000))
    assert [(t["mid"], t["text"], t["cost"]) for t in spend.turns(sid)][-1] == (mid, "next task", 1.0)


def test_summaries_are_counted(cfg, store, repo):
    agent = Agent(price_all(cfg), store, llm=FakeLLM([[{"text": "one"}], [{"text": "two"}], [{"text": "three"}]]))
    sess = store.create_session(str(repo), "main")
    for text in ("first", "second", "third"):
        list(agent.chat(sess.id, text))
    before = sum(r["calls"] for r in store.usage(sess.id)["by_model"])
    assert [e["cost"] > 0 for e in agent.compact(sess.id) if e["type"] == "usage"] == [True]
    assert sum(r["calls"] for r in store.usage(sess.id)["by_model"]) == before + 1


def test_second_opinions_are_counted_and_skipped_at_the_cap(cfg, store, repo):
    agent = Agent(replace(priced(cfg), daily_budget=10.0), store, llm=FakeLLM([]))
    agent.auto_model = lambda tier: "advisor-model" if tier == "hard" else "main-model"
    tu = {"name": "run_tests", "toolUseId": "t", "input": {}}
    failing = "exit code 1 in 0.1s"
    sess = store.create_session(str(repo), "auto")
    list(agent._after_result(sess.id, tu, failing, False))
    events = list(agent._after_result(sess.id, tu, failing, False))
    assert [e["type"] for e in events] == ["notice", "usage", "advisor"] and events[1]["model"] == "advisor-model"
    assert [r["model"] for r in store.usage(sess.id)["by_model"]] == ["advisor-model"]
    calls = len(agent.llm.calls)
    sess = store.create_session(str(repo), "auto")
    store.add_usage(sess.id, SONNET, usage(input=5_000_000))
    list(agent._after_result(sess.id, tu, failing, False))
    assert list(agent._after_result(sess.id, tu, failing, False)) == [] and len(agent.llm.calls) == calls


def test_a_summary_that_reaches_the_cap_stops_before_the_next_call(cfg, store, repo):
    agent = Agent(replace(priced(cfg), daily_budget=10.0), store, llm=FakeLLM([[{"text": "unreached"}]]))
    sid = store.create_session(str(repo), "main").id

    def summarises(*_):
        store.add_usage(sid, SONNET, usage(input=5_000_000))
        return True
        yield

    agent.ctxm.ensure_room = summarises
    events = list(agent.chat(sid, "go"))
    assert [e["type"] for e in events if e["type"] in ("budget", "done")] == ["budget", "done"] and not agent.llm.calls


def test_manual_compaction_waits_at_the_cap(cfg, store, repo):
    agent = Agent(replace(priced(cfg), daily_budget=10.0), store, llm=FakeLLM([[{"text": "one"}]]))
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "first"))
    store.add_usage(sess.id, SONNET, usage(input=5_000_000))
    events = list(agent.compact(sess.id))
    assert any(e["type"] == "budget" for e in events) and events[-1]["type"] == "done"
    assert not [c for c in agent.llm.calls if "complete" in c]


def test_carrying_a_session_over_waits_at_the_cap_rather_than_lose_its_work(cfg, store, repo):
    agent = Agent(replace(priced(cfg), daily_budget=10.0), store, llm=FakeLLM([]))
    sid = store.create_session(str(repo), "main").id
    client = TestClient(create_app(replace(priced(cfg), daily_budget=10.0), store, agent))
    store.add_usage(sid, SONNET, usage(input=5_000_000))
    headers = {"X-Codepilot": "1"}
    response = client.post(f"/api/sessions/{sid}/handoff", headers=headers)
    assert response.status_code == 409 and "budget" in response.json()["error"]
    client.post("/api/budget/override", headers=headers)
    assert client.post(f"/api/sessions/{sid}/handoff", headers=headers).status_code == 200


def test_every_provider_reports_what_a_one_shot_call_used():
    from codepilot.anthropic_api import AnthropicAPI
    from codepilot.bedrock import Bedrock
    from codepilot.ollama import Ollama
    from codepilot.openai_api import OpenAIAPI

    used = {"inputTokens": 3}
    for cls in (AnthropicAPI, Bedrock, Ollama, OpenAIAPI):
        llm = cls.__new__(cls)
        llm.stream = lambda *_a, **_k: iter([{"type": "message", "content": [{"text": "hi"}], "usage": used}])
        seen = []
        assert llm.complete("m", "s", "p", on_usage=seen.append) == "hi" and seen == [used]
        assert llm.complete("m", "s", "p") == "hi"


def test_explore_reports_its_cost_and_its_warning(cfg, store, repo):
    llm = FakeLLM([[tool_use("e1", "explore", task="look")], [{"text": "report"}], [{"text": "done"}]])
    agent = Agent(replace(price_all(cfg), daily_budget=1_000_000.0), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    answers = iter(["ok", "warn", "ok", "ok"])
    agent.spend.check = lambda: next(answers, "ok")
    events = list(agent.chat(sess.id, "explore"))
    usage = [e for e in events if e["type"] == "usage"]
    assert len(usage) == 3 and all(e["cost"] > 0 for e in usage)
    assert any(e["type"] == "notice" and "daily budget" in e["message"] for e in events)
