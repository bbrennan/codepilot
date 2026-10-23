"""Proposals that can no longer apply stop waiting for review: superseded, outdated, discarded."""

import json

from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot.agent import Agent, history_events
from codepilot.server import create_app

H = {"X-Codepilot": "1"}


def setup(cfg, store, script):
    agent = Agent(cfg, store, llm=FakeLLM(script))
    client = TestClient(create_app(cfg, store, agent))
    return agent, client


def statuses(store, sid):
    return {p.id: p.status for p in store.list_proposals(sid)}


def test_a_new_version_of_the_same_change_supersedes_the_old_one(cfg, store, repo):
    agent, _ = setup(cfg, store, [
        [tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
        [{"text": "proposed"}],
        [tool_use("t2", "propose_edit", path="agent/core.py", old_text="a - b", new_text="b + a")],
        [{"text": "proposed again"}],
    ])
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "fix"))
    events = list(agent.chat(sess.id, "write it the other way round"))
    assert statuses(store, sess.id) == {1: "superseded", 2: "pending"}
    assert any(e["type"] == "proposal" and e["proposal"]["id"] == 1 and e["proposal"]["status"] == "superseded"
               for e in events)


def test_applying_one_change_retires_overlapping_ones(cfg, store, repo):
    agent, client = setup(cfg, store, [
        [tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b"),
         tool_use("t2", "propose_edit", path="agent/core.py", old_text="    return a - b",
                  new_text="    return sum((a, b))")],
        [{"text": "two options"}],
        [{"text": "noted"}],
    ])
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "fix"))
    r = client.post("/api/proposals/2/apply", headers=H).json()
    assert r["status"] == "applied" and [o["id"] for o in r["outdated"]] == [1]
    assert statuses(store, sess.id) == {1: "outdated", 2: "applied"}
    list(agent.chat(sess.id, "thanks"))  # the model is told, so it doesn't wait for #1
    sent = json.dumps(agent.llm.calls[-1]["messages"][-1])
    assert "Proposal #1 (agent/core.py) is outdated" in sent and "Proposal #2 (agent/core.py) was applied" in sent


def test_reload_retires_changes_made_stale_outside_codepilot(cfg, store, repo):
    agent, client = setup(cfg, store, [
        [tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
        [{"text": "proposed"}],
    ])
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "fix"))
    (repo / "agent/core.py").write_text("def add(a, b):\n    return b + a\n")  # fixed by hand in an editor
    data = client.get(f"/api/sessions/{sess.id}").json()
    assert [p["status"] for p in data["proposals"]] == ["outdated"]


def test_applied_changes_stay_applied_and_replay_in_place(cfg, store, repo):
    agent, client = setup(cfg, store, [
        [tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
        [{"text": "done"}],
    ])
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "fix"))
    client.post("/api/proposals/1/apply", headers=H)
    fresh = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))  # "relaunch"
    data = fresh.get(f"/api/sessions/{sess.id}").json()
    assert [p["status"] for p in data["proposals"]] == ["applied"]
    kinds = [e["type"] for e in history_events(store, sess.id)]
    assert kinds.index("proposal_ref") == kinds.index("tool_result") + 1  # right after the tool call


def test_rewinding_discards_changes_proposed_after_that_point(cfg, store, repo):
    agent, _ = setup(cfg, store, [
        [{"text": "hello"}],
        [tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
        [{"text": "proposed"}],
        [{"text": "ok, different approach"}],
    ])
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "hi"))
    mid = next(e["mid"] for e in list(agent.chat(sess.id, "fix it")) if e["type"] == "turn")
    events = list(agent.rewind(sess.id, mid, "actually, just explain it"))
    assert {"type": "proposals_changed", "ids": [1]} in events
    assert statuses(store, sess.id) == {1: "discarded"}
