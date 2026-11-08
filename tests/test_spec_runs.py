"""A spec run's card is kept with the session, so a reload draws it where it was, and Edit/Retry take back what the
rewound messages did to it. (Spec in-chat-progress, task 5: 3.1-3.3.)"""

from dataclasses import replace

import pytest
from fakes import FakeLLM
from starlette.testclient import TestClient

from codepilot import spec_runs
from codepilot.agent import Agent, history_events
from codepilot.server import create_app

H = {"X-Codepilot": "1"}


def card(*statuses, ended=None):
    items = [{"text": f"{i + 1}. Task {i + 1}", "status": s} for i, s in enumerate(statuses)]
    return {"run": "r1", "spec": "demo", "items": items, "ended": ended}


def test_a_reload_shows_each_state_of_the_card_where_it_happened(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([[{"text": "did one"}], [{"text": "did two"}]]))
    sess = store.create_session(str(repo), "main")
    spec_runs.record(store, sess.id, card("doing", "todo"))  # before the first task's message
    list(agent.chat(sess.id, "Implement task 1"))
    spec_runs.record(store, sess.id, card("done", "doing"))
    list(agent.chat(sess.id, "Implement task 2"))
    spec_runs.record(store, sess.id, card("done", "done", ended="complete"))
    story = [(e["type"], e.get("text") or [i["status"] for i in e.get("items", [])])
             for e in history_events(store, sess.id) if e["type"] in ("user", "assistant", "spec_run")]
    assert story == [
        ("spec_run", ["doing", "todo"]), ("user", "Implement task 1"), ("assistant", "did one"),
        ("spec_run", ["done", "doing"]), ("user", "Implement task 2"), ("assistant", "did two"),
        ("spec_run", ["done", "done"]),
    ]
    assert [e for e in history_events(store, sess.id) if e["type"] == "spec_run"][-1]["ended"] == "complete"


def test_a_rewind_forgets_what_the_card_said_after_that_message(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([[{"text": "did one"}], [{"text": "did two"}], [{"text": "again"}]]))
    sess = store.create_session(str(repo), "main")
    spec_runs.record(store, sess.id, card("doing", "todo"))
    list(agent.chat(sess.id, "Implement task 1"))
    spec_runs.record(store, sess.id, card("done", "doing"))
    list(agent.chat(sess.id, "Implement task 2"))
    spec_runs.record(store, sess.id, card("done", "paused", ended="paused"))
    second = next(e["mid"] for e in history_events(store, sess.id) if e.get("text") == "Implement task 2")
    list(agent.rewind(sess.id, second, "Implement task 2"))  # Retry
    runs = [e for e in history_events(store, sess.id) if e["type"] == "spec_run"]
    assert [[i["status"] for i in e["items"]] for e in runs] == [["doing", "todo"], ["done", "doing"]]


@pytest.mark.parametrize("bad", [
    {},
    {**card("doing"), "items": "1. Task"},
    {**card("doing"), "items": [{"text": "1. Task", "status": "bogus"}]},
    {**card("doing"), "ended": "exploded"},
    {**card("doing"), "spec": ""},
    {**card("doing"), "items": [{"text": "x" * 2000, "status": "todo"}]},
    {**card("doing"), "items": [{"text": "1. Task", "status": ["done"]}]},  # not a string (unhashable)
    {**card("doing"), "ended": {"why": "x"}},
])
def test_a_malformed_card_is_refused(cfg, store, repo, bad):
    sess = store.create_session(str(repo), "main")
    with pytest.raises(ValueError):
        spec_runs.record(store, sess.id, bad)
    assert not [e for e in history_events(store, sess.id) if e["type"] == "spec_run"]


def test_the_browser_records_the_card_and_a_session_load_replays_it(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([[{"text": "did one"}]]))
    client = TestClient(create_app(replace(cfg, terminal=False), store, agent))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    sent = {**card("doing"), "items": [{"text": "1. Task 1", "status": "done", "note": "tests pass"}]}
    resp = client.post(f"/api/sessions/{sid}/spec-run", json=sent, headers=H)
    assert resp.status_code == 200 and resp.json() == {"type": "spec_run", **sent}
    assert client.post(f"/api/sessions/{sid}/spec-run", json={"run": "r1"}, headers=H).status_code == 400
    events = client.get(f"/api/sessions/{sid}").json()["events"]
    assert [e for e in events if e["type"] == "spec_run"] == [{"type": "spec_run", **sent}]
