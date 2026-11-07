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
    assert plans.normalize("Read it\n  Fix it\n") == [{"text": "Read it", "status": "todo"},  # lines, as execute()
                                                     {"text": "Fix it", "status": "todo"}]
    assert plans.normalize(None) == [] and plans.normalize({"text": "x"}) == []
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


def test_a_plan_that_arrives_already_done_is_complete():
    assert plans.step(None, A_DONE)["kind"] == "complete"
    b_done = [{**i, "status": "done"} for i in B]
    replaced = plans.step(A_DOING, b_done)
    assert replaced["kind"] == "complete" and replaced["retired"]["progress"] == [1, 2]


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


def test_calls_that_failed_are_not_part_of_the_plans_story(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([
        [tool_use("t0", "update_plan", items=A)], [{"text": "planned"}],
        [tool_use("t1", "update_plan")], [{"text": "oops"}],  # no items: rejected, the plan stays A
        [tool_use("t2", "update_plan", items=A_DOING)], [{"text": "progress"}],
    ]))
    sess = store.create_session(str(repo), "main")
    live = []
    for text in ("plan", "bad call", "progress"):
        live += [e for e in agent.chat(sess.id, text) if e["type"] == "plan"]
    assert [e["kind"] for e in live] == ["new", "update"]  # the bad call changed nothing
    replay = [e for e in history_events(store, sess.id) if e["type"] == "plan"]
    assert replay == live
    assert plans.current(store, sess.id)["items"] == A_DOING


def test_two_updates_in_one_response_follow_each_other(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([
        [tool_use("t0", "update_plan", items=A), tool_use("t1", "update_plan", items=A_DOING)], [{"text": "ok"}]]))
    sess = store.create_session(str(repo), "main")
    live = [e for e in agent.chat(sess.id, "plan twice") if e["type"] == "plan"]
    assert [e["kind"] for e in live] == ["new", "update"]
    assert [e for e in history_events(store, sess.id) if e["type"] == "plan"] == live


# -- dismissing a paused plan --------------------------------------------------------------------------------------


def _paused(cfg, store, repo, *more):
    """A turn that ended with its plan unfinished: step 2 of 2 still in progress."""
    agent = Agent(cfg, store, llm=FakeLLM([[tool_use("p1", "update_plan", items=A_DOING)], [{"text": "stopped"}],
                                           *more]))
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "make a plan"))
    return agent, sess


def test_dismissing_a_paused_plan_retires_it_and_a_reload_agrees(cfg, store, repo):
    agent, sess = _paused(cfg, store, repo)
    event = plans.dismiss(store, sess.id)
    assert event["kind"] == "clear" and event["dismissed"] and event["retired"]["progress"] == [1, 2]
    assert plans.current(store, sess.id)["items"] == []
    redrawn = [e for e in history_events(store, sess.id) if e["type"] == "plan"]
    assert redrawn[-1]["kind"] == "clear" and redrawn[-1]["dismissed"]
    assert plans.dismiss(store, sess.id) is None  # nothing left to dismiss



def test_a_reload_puts_a_dismissal_where_it_happened_after_the_turn(cfg, store, repo):
    # You dismiss once the turn has ended, so the work after the plan's last update came before the dismissal.
    agent = Agent(cfg, store, llm=FakeLLM([[tool_use("p1", "update_plan", items=A_DOING)],
                                           [tool_use("r1", "read_file", path="agent/core.py")], [{"text": "stopped"}]]))
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "make a plan"))
    plans.dismiss(store, sess.id)
    order = [(e["type"], e.get("kind") or e.get("name")) for e in history_events(store, sess.id)
             if e["type"] in ("plan", "tool_call")]
    assert order == [("tool_call", "update_plan"), ("plan", "new"), ("tool_call", "read_file"), ("plan", "clear")]


def test_after_a_dismissal_the_next_update_starts_a_new_plan(cfg, store, repo):
    agent, sess = _paused(cfg, store, repo, [tool_use("p2", "update_plan", items=A)], [{"text": "ok"}])
    plans.dismiss(store, sess.id)
    plan = next(e for e in agent.chat(sess.id, "start over") if e["type"] == "plan")
    assert plan["kind"] == "new" and plan["retired"] is None  # not an update of the plan you put away


def test_a_dismissal_belongs_to_that_plan_even_after_an_edit(cfg, store, repo):
    agent, sess = _paused(cfg, store, repo, [tool_use("p2", "update_plan", items=B)], [{"text": "ok"}])
    plans.dismiss(store, sess.id)
    first = next(mid for mid, m in store.messages(sess.id) if m["role"] == "user")
    list(agent.rewind(sess.id, first, "make a different plan"))  # the dismissed update is gone with its turn
    assert plans.current(store, sess.id)["items"] == B


def test_the_model_is_told_once_that_its_plan_was_dismissed(cfg, store, repo):
    agent, sess = _paused(cfg, store, repo, [{"text": "ok"}], [{"text": "ok"}])
    plans.dismiss(store, sess.id)
    list(agent.chat(sess.id, "thanks"))
    list(agent.chat(sess.id, "bye"))

    def told(call):
        return sum("dismissed your plan" in b.get("text", "") for b in call["messages"][-1]["content"])

    assert told(agent.llm.calls[-2]) == 1 and told(agent.llm.calls[-1]) == 0
