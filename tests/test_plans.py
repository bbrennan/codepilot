"""The session plan (update_plan): one lifecycle for the live view, the transcript and a reload."""

from fakes import FakeLLM, tool_use

from codepilot import plans
from codepilot.agent import Agent, history_events

A = [{"text": "Write tests", "status": "todo"}, {"text": "Implement export", "status": "todo"}]
A_DOING = [{"text": "Write tests", "status": "done"}, {"text": "Implement export", "status": "doing"}]
A_DONE = [{"text": "Write tests", "status": "done"}, {"text": "Implement export", "status": "done"}]
B = [{"text": "Profile the query", "status": "doing"}, {"text": "Add an index", "status": "todo"}]


def test_normalize_accepts_what_models_send():
    assert plans.normalize(["Read it", {"text": "Fix it", "status": "bogus"}]) == [
        {"text": "Read it", "status": "todo"}, {"text": "Fix it", "status": "todo"}]
    assert plans.normalize('["Read it"]') == [{"text": "Read it", "status": "todo"}]  # a JSON string
    assert plans.normalize("not json") == [] and plans.normalize(None) == []
    assert plans.normalize([{"text": "  ", "status": "done"}]) == []  # blank items are dropped


def test_step_tells_updates_from_new_plans_and_says_what_changed():
    first = plans.step(None, A)
    assert first["kind"] == "new" and first["retired"] is None and first["progress"] == [0, 2]
    update = plans.step(A, A_DOING)
    assert update["kind"] == "update" and update["changes"] == ["✓ Write tests", "→ Implement export"]
    done = plans.step(A_DOING, A_DONE)
    assert done["kind"] == "complete" and done["changes"] == ["✓ Implement export"]
    replaced = plans.step(A_DOING, B)
    assert replaced["kind"] == "new" and replaced["retired"] == {"items": A_DOING, "progress": [1, 2]}
    after_done = plans.step(A_DONE, A)  # the same steps again after finishing: a fresh plan, not an update
    assert after_done["kind"] == "new" and after_done["retired"] is None
    cleared = plans.step(A_DOING, [])
    assert cleared["kind"] == "clear" and cleared["retired"]["progress"] == [1, 2]


def test_summary_is_what_the_tool_returns():
    assert plans.summary(plans.step(A, A_DOING)) == "Plan updated (1 of 2 done): ✓ Write tests · → Implement export"
    assert plans.summary(plans.step(None, A)) == "New plan (0 of 2 done)."
    assert plans.summary(plans.step(A_DOING, A_DONE)).startswith("Plan complete (2 of 2 done)")


def _session(cfg, store, repo, *plan_items):
    script = []
    for i, items in enumerate(plan_items):
        script += [[tool_use(f"t{i}", "update_plan", items=items)], [{"text": f"step {i}"}]]
    agent = Agent(cfg, store, llm=FakeLLM(script))
    sess = store.create_session(str(repo), "main")
    live = []
    for i in range(len(plan_items)):
        live += [e for e in agent.chat(sess.id, f"go {i}") if e["type"] == "plan"]
    return agent, sess, live


def test_live_events_and_a_reload_tell_the_same_story(cfg, store, repo):
    _, sess, live = _session(cfg, store, repo, A, A_DOING, B, [])
    assert [e["kind"] for e in live] == ["new", "update", "new", "clear"]
    replay = [e for e in history_events(store, sess.id) if e["type"] == "plan"]
    assert replay == live


def test_a_plan_sent_as_a_json_string_survives_a_reload(cfg, store, repo):
    import json
    _, sess, live = _session(cfg, store, repo, json.dumps(["Read it", "Fix it"]))
    replay = [e for e in history_events(store, sess.id) if e["type"] == "plan"]
    assert replay == live and replay[0]["items"] == [{"text": "Read it", "status": "todo"},
                                                     {"text": "Fix it", "status": "todo"}]


def test_rewinding_restores_the_plan_as_it_was(cfg, store, repo):
    agent, sess, _ = _session(cfg, store, repo, A, B)
    agent.llm.script.append([{"text": "redone"}])
    second = next(e["mid"] for e in history_events(store, sess.id) if e["type"] == "user" and e["text"] == "go 1")
    events = list(agent.rewind(sess.id, second, "something else"))
    restored = next(e for e in events if e["type"] == "plan")
    assert restored["kind"] == "restore" and restored["items"] == A
