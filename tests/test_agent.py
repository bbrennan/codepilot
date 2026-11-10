from dataclasses import replace

from fakes import FakeLLM, tool_use

from codepilot.agent import Agent, history_events, is_user_turn


def types(events):
    return [e["type"] for e in events]


def test_tool_loop_round_trip(cfg, store, repo):
    llm = FakeLLM([
        [{"text": "Looking."}, tool_use("t1", "read_file", path="agent/core.py")],
        [{"text": "`add` subtracts: agent/core.py:2"}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "review core"))
    assert types(events).count("tool_result") == 1
    assert types(events)[-1] == "done"
    result = next(e for e in events if e["type"] == "tool_result")
    assert "return a - b" in result["output"] and not result["is_error"]
    # Second model call saw the tool result in Converse shape.
    second = llm.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[2]["content"][0]["toolResult"]["toolUseId"] == "t1"
    assert store.get_session(sess.id).title == "review core"
    assert store.usage(sess.id)["by_model"][0]["calls"] == 2


def test_approval_pause_and_resume(cfg, store, repo):
    llm = FakeLLM([
        [tool_use("t1", "list_files"), tool_use("t2", "run_tests", args="-k add")],
        [{"text": "Tests done."}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "run the tests"))
    assert types(events)[-1] == "approval_needed"
    assert events[-1]["tools"][0]["command"] == f"{cfg.test_cmd} -k add"
    assert store.get_session(sess.id).pending is not None

    events = list(agent.resume(sess.id, approve=True))
    result = next(e for e in events if e["type"] == "tool_result")
    assert "tests-ran" in result["output"]
    assert store.get_session(sess.id).pending is None
    # Both results returned together, in the original call order.
    results_msg = llm.calls[1]["messages"][2]["content"]
    assert [b["toolResult"]["toolUseId"] for b in results_msg] == ["t1", "t2"]


def test_denied_tool_reports_error(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "run_command", command="make eval")], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "eval"))
    events = list(agent.resume(sess.id, approve=False))
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] and "declined" in result["output"]


def test_auto_approve_session_runs_tests(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "run_tests")], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main", auto_approve=True)
    events = list(agent.chat(sess.id, "test"))
    assert "approval_needed" not in types(events)


def test_proposal_outcome_reported_on_next_turn(cfg, store, repo):
    llm = FakeLLM([
        [tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
        [{"text": "Proposed."}],
        [{"text": "Thanks."}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "fix it"))
    assert any(e["type"] == "proposal" for e in events)
    store.set_proposal_status(1, "applied")
    list(agent.chat(sess.id, "done"))
    last_user = llm.calls[-1]["messages"][-1]["content"]
    assert last_user[0]["text"] == "done"
    assert "Proposal #1 (agent/core.py) was applied by the user." in last_user[-1]["text"]


def test_compaction_summarises_old_turns(cfg, store, repo):
    cfg = replace(cfg, prune_at=0.0, compact_at=0.0)  # compact at every turn boundary
    llm = FakeLLM([[{"text": f"answer {i} " * 5}] for i in range(6)])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    for i in range(6):
        list(agent.chat(sess.id, f"question {i}"))
    s = store.get_session(sess.id)
    assert s.summary.startswith("SUMMARY: earlier work") and "> question 0" in s.summary
    live = store.live_messages(sess.id)
    assert is_user_turn(live[0])
    assert len(store.messages(sess.id, include_archived=True)) > len(live)
    # Summary reaches the model via the system prompt; full history still renders in the UI.
    assert any("SUMMARY: earlier work" in b["text"] for b in llm.calls[-1]["system"])
    assert len([e for e in history_events(store, sess.id) if e["type"] == "user"]) == 6


def test_unknown_tool_and_missing_repo(cfg, store, repo, tmp_path):
    llm = FakeLLM([[tool_use("t1", "rm_rf")], [{"text": "sorry"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "x"))
    assert next(e for e in events if e["type"] == "tool_result")["is_error"]
    gone = store.create_session(str(tmp_path / "missing"), "main")
    assert types(list(Agent(cfg, store, llm=FakeLLM([])).chat(gone.id, "x"))) == ["turn", "error"]


def test_no_workspace_then_open_workspace(cfg, store, repo):
    llm = FakeLLM([
        [tool_use("t1", "list_files")],
        [tool_use("t2", "open_workspace", path=str(repo))],
        [tool_use("t3", "read_file", path="agent/core.py")],
        [{"text": "done"}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session("", "main")
    events = list(agent.chat(sess.id, f"look at {repo}"))
    first = next(e for e in events if e["type"] == "tool_result")
    assert first["is_error"] and "open_workspace" in first["output"]
    assert events[-1]["type"] == "approval_needed"
    assert events[-1]["tools"][0]["command"] == f"open workspace {repo}"
    assert any("none open yet" in b["text"] for b in llm.calls[0]["system"])

    events = list(agent.resume(sess.id, approve=True))
    assert any(e["type"] == "workspace" for e in events)
    assert store.get_session(sess.id).repo == str(repo.resolve())
    read = [e for e in events if e["type"] == "tool_result" and e["name"] == "read_file"][0]
    assert "return a - b" in read["output"]
    # The system prompt was rebuilt for the new workspace mid-loop.
    assert any(f"Workspace: {repo.resolve()}" in b["text"] for b in llm.calls[-1]["system"])


def test_explore_subagent_keeps_raw_reads_out_of_main_context(cfg, store, repo):
    llm = FakeLLM([
        [tool_use("m1", "explore", task="where is add defined?")],
        # sub-agent turns
        [tool_use("s1", "search_code", pattern="def add"), tool_use("s2", "run_command", command="rm -rf /")],
        [{"text": "add is at agent/core.py:1 and subtracts."}],
        # main agent final
        [{"text": "Found it."}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "where is add?"))
    subs = [e for e in events if e["type"] == "sub_tool"]
    assert [e["name"] for e in subs] == ["search_code", "run_command"]
    report = next(e for e in events if e["type"] == "tool_result" and e["name"] == "explore")
    assert report["output"] == "add is at agent/core.py:1 and subtracts."
    sub_call = llm.calls[1]
    assert sub_call["model"] == cfg.models["fast"]
    assert {t["name"] for t in sub_call["tools"]} >= {"read_file", "search_code"}
    assert not {"run_command", "propose_edit", "explore", "open_workspace"} & {t["name"] for t in sub_call["tools"]}
    # The sub-agent's refused run_command came back as an error, not executed.
    sub_results = llm.calls[2]["messages"][-1]["content"]
    assert sub_results[1]["toolResult"]["status"] == "error"
    # Main conversation only holds the report, not the search output.
    main_msgs = store.live_messages(sess.id)
    assert "def add" not in str(main_msgs)


def test_update_plan_emits_event_and_replays(cfg, store, repo):
    items = [{"text": "read code", "status": "done"}, {"text": "fix", "status": "doing"}]
    llm = FakeLLM([[tool_use("t1", "update_plan", items=items)], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "plan it"))
    assert next(e for e in events if e["type"] == "plan")["items"] == items
    assert any(e["type"] == "plan" for e in history_events(store, sess.id))


def test_stop_mid_turn_then_continue(cfg, store, repo):
    class StoppingLLM(FakeLLM):
        def stream(self, model, system, messages, tools=None, max_tokens=None):
            if len(self.calls) == 0:
                agent.cancel(sess.id)  # user presses Stop while the first reply streams
            yield from super().stream(model, system, messages, tools, max_tokens)

    llm = StoppingLLM([[{"text": "partial answer"}], [{"text": "fresh answer"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "first"))
    assert any(e["type"] == "notice" and e["message"] == "Stopped." for e in events)
    assert [m["role"] for m in store.live_messages(sess.id)] == ["user", "assistant"]
    events = list(agent.chat(sess.id, "second"))
    assert any(e.get("text") == "fresh answer" for e in events)


def test_consecutive_user_messages_are_merged(cfg, store, repo):
    llm = FakeLLM([[{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    store.add_message(sess.id, "user", [{"text": "left over after an error"}])
    list(agent.chat(sess.id, "next question"))
    roles = [m["role"] for m in llm.calls[0]["messages"]]
    assert roles == ["user"]
    texts = [b["text"] for b in llm.calls[0]["messages"][0]["content"]]
    assert texts[:2] == ["left over after an error", "next question"] and texts[2].startswith("<turn_context>")


def test_plan_mode_blocks_edits_and_slash_skill(cfg, store, repo):
    llm = FakeLLM([
        [tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b"),
         tool_use("t2", "read_file", path="agent/core.py")],
        [{"text": "Plan: 1. fix the operator"}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, mode="plan")
    events = list(agent.chat(sess.id, "/grill the fix"))
    assert events[0] == {"type": "skill", "name": "grill"}
    results = {e["name"]: e for e in events if e["type"] == "tool_result"}
    assert results["propose_edit"]["is_error"] and "disabled in Plan mode" in results["propose_edit"]["output"]
    assert not results["read_file"]["is_error"]
    assert store.list_proposals(sess.id) == []
    system = " ".join(b["text"] for b in llm.calls[0]["system"])
    assert "Repository map" in system and "- grill:" not in system and "PLAN MODE" not in system
    turn = llm.calls[0]["messages"][0]["content"][-1]["text"]
    assert turn.startswith("<turn_context>") and "PLAN MODE:" in turn
    assert '<skill name="plan-feature">' in turn  # the mode preloads its skill
    sent = llm.calls[0]["messages"][0]["content"]
    assert sent[1]["text"].startswith('<skill name="grill">')
    assert history_events(store, sess.id)[1] == {"type": "skill", "name": "grill"}


def test_system_prompt_frozen_and_reasoning_stripped_at_boundary(cfg, store, repo):
    reasoning = {"reasoningContent": {"reasoningText": {"text": "", "signature": "sig"}}}
    llm = FakeLLM([[reasoning, {"text": f"answer {i}"}] for i in range(4)])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "one"))
    (repo / "agent" / "new_module.py").write_text("def brand_new():\n    pass\n")  # repo map would change
    store.update_session(sess.id, mode="review")
    list(agent.chat(sess.id, "two"))
    # Same system prompt bytes on both turns; mode change arrives in the user message instead.
    assert llm.calls[0]["system"] == llm.calls[1]["system"]
    assert "REVIEW MODE" in llm.calls[1]["messages"][-1]["content"][-1]["text"]
    assert "Mode: Review (unchanged)" not in llm.calls[1]["messages"][-1]["content"][-1]["text"]
    # Earlier reasoning is replayed unchanged while the prefix is stable.
    assert llm.calls[1]["messages"][1]["content"][0] == reasoning
    # A boundary (memory compaction changes the summary) rebuilds the system and drops old reasoning once.
    store.update_session(sess.id, summary="earlier work")
    list(agent.chat(sess.id, "three"))
    assert llm.calls[2]["system"] != llm.calls[1]["system"]
    assert not any("reasoningContent" in b for m in llm.calls[2]["messages"] for b in m["content"])
    list(agent.chat(sess.id, "four"))
    assert llm.calls[3]["system"] == llm.calls[2]["system"]
    assert llm.calls[3]["messages"][-2]["content"][0] == reasoning  # new reasoning is kept again


def test_reopening_current_workspace_needs_no_approval(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "open_workspace", path=str(repo))], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "look at this repo"))
    assert "approval_needed" not in types(events)
    assert not next(e for e in events if e["type"] == "tool_result")["is_error"]


def test_a_message_while_an_approval_waits_declines_it_and_carries_the_message(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "run_command", command="rm -rf build")], [{"text": "ok, I won't"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    assert types(list(agent.chat(sess.id, "clean up")))[-1] == "approval_needed"
    events = list(agent.chat(sess.id, "don't delete anything, just list it"))
    assert events[0]["type"] == "notice" and "Declined" in events[0]["message"]
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] and "declined" in result["output"]
    sent = llm.calls[-1]["messages"][-1]["content"]
    assert sent[-1] == {"text": "don't delete anything, just list it"} and "toolResult" in sent[0]
    assert store.get_session(sess.id).pending is None and types(events)[-1] == "done"


# -- verification receipts ----------------------------------------------------------------------------------------

def _propose_then(*more):
    return FakeLLM([[tool_use("p1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
                    *more])


def test_verify_changes_needs_approval_unless_tests_auto_run(cfg, store, repo):
    agent = Agent(cfg, store, llm=_propose_then([tool_use("v1", "verify_changes")]))
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "fix and verify"))
    waiting = next(e for e in events if e["type"] == "approval_needed")["tools"][0]
    assert waiting["name"] == "verify_changes" and "verify pending changes" in waiting["command"]
    assert store.latest_receipt(sess.id) is None


def test_verify_changes_tests_the_pending_changes_and_tells_the_agent(cfg, store, repo):
    agent = Agent(cfg, store, llm=_propose_then([tool_use("v1", "verify_changes")], [{"text": "verified"}]))
    sess = store.create_session(str(repo), "main", auto_approve=True)
    events = list(agent.chat(sess.id, "fix and verify"))
    result = next(e for e in events if e["type"] == "tool_result" and e["name"] == "verify_changes")
    assert not result["is_error"] and result["output"].startswith("Verified pending change #1: pass")
    receipts = [e["receipt"] for e in events if e["type"] == "verification"]
    assert len(receipts) == 1 and receipts[0]["status"] == "pass" and receipts[0]["proposal_ids"] == [1]
    assert store.latest_receipt(sess.id)["told"] is True  # it saw the result; no repeat in the turn context
    assert "a - b" in (repo / "agent/core.py").read_text()  # still only proposed


def test_a_turn_that_leaves_changes_pending_is_verified_when_tests_auto_run(cfg, store, repo):
    agent = Agent(cfg, store, llm=_propose_then([{"text": "proposed"}], [{"text": "next"}]))
    sess = store.create_session(str(repo), "main", auto_approve=True)
    events = list(agent.chat(sess.id, "fix"))
    kinds = types(events)
    assert "verification" in kinds and kinds.index("verification") < kinds.index("done")
    assert store.latest_receipt(sess.id)["told"] is False
    list(agent.chat(sess.id, "thanks"))  # the model hears the receipt once, with the next message
    sent = " ".join(b.get("text", "") for b in agent.llm.calls[-1]["messages"][-1]["content"])
    assert "Verification of your pending changes #1: pass" in sent
    assert store.latest_receipt(sess.id)["told"] is True


def test_no_automatic_verification_without_auto_run_or_when_already_verified(cfg, store, repo):
    agent = Agent(cfg, store, llm=_propose_then([{"text": "proposed"}]))
    sess = store.create_session(str(repo), "main")
    assert "verification" not in types(agent.chat(sess.id, "fix"))
    agent = Agent(cfg, store, llm=_propose_then([tool_use("v1", "verify_changes")], [{"text": "verified"}]))
    sess = store.create_session(str(repo), "main", auto_approve=True)
    assert types(agent.chat(sess.id, "fix and verify")).count("verification") == 1  # not again at the end


def test_verification_can_be_switched_off(cfg, store, repo):
    agent = Agent(replace(cfg, verify=False), store, llm=_propose_then([{"text": "proposed"}]))
    sess = store.create_session(str(repo), "main", auto_approve=True)
    assert "verification" not in types(agent.chat(sess.id, "fix"))
    assert "verify_changes" not in agent.tools


# -- external content (taint) -------------------------------------------------------------------------------------

def _docs_agent(cfg, store, script):
    agent = Agent(cfg, store, llm=FakeLLM(script))
    agent.tools["library_docs"].fn = lambda ctx, library, question: "docs text"  # no network in tests
    return agent


def _taint(store, sid):
    return (store.get_session(sid).context_state or {}).get("taint", [])


def test_reading_external_content_marks_the_session_once_per_source(cfg, store, repo):
    agent = _docs_agent(cfg, store, [
        [tool_use("t1", "library_docs", library="fastapi", question="a")],
        [tool_use("t2", "library_docs", library="fastapi", question="b")],
        [tool_use("t3", "library_docs", library="boto3", question="c")], [{"text": "done"}]])
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "look it up"))
    for _ in range(2):  # once the session is tainted, further lookups ask
        events += list(agent.resume(sess.id, True))
    marks = [e for e in events if e["type"] == "taint"]
    assert [[s["detail"] for s in e["sources"]] for e in marks] == [["docs fastapi"], ["docs fastapi", "docs boto3"]]
    assert [s["detail"] for s in _taint(store, sess.id)] == ["docs fastapi", "docs boto3"]


def test_workspace_reads_leave_the_session_clean(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([[tool_use("t1", "read_file", path="agent/core.py")], [{"text": "ok"}]]))
    sess = store.create_session(str(repo), "main")
    assert "taint" not in types(agent.chat(sess.id, "read it")) and _taint(store, sess.id) == []


def test_the_explore_sub_agent_can_taint_the_session(cfg, store, repo):
    agent = _docs_agent(cfg, store, [
        [tool_use("e1", "explore", task="find docs")],
        [tool_use("d1", "library_docs", library="fastapi", question="q")], [{"text": "report"}],  # the sub-agent
        [{"text": "done"}]])
    sess = store.create_session(str(repo), "main")
    assert "taint" in types(agent.chat(sess.id, "explore it"))
    assert _taint(store, sess.id)[0]["detail"] == "docs fastapi"


def test_taint_survives_later_turns_a_restart_and_compaction_but_not_a_new_session(cfg, store, repo):
    from codepilot.store import Store
    agent = _docs_agent(cfg, store, [
        [tool_use("t1", "library_docs", library="fastapi", question="a")], [{"text": "one"}], [{"text": "two"}]])
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "look it up"))
    list(agent.chat(sess.id, "thanks"))
    list(agent.compact(sess.id))
    assert [s["detail"] for s in _taint(Store(cfg.home), sess.id)] == ["docs fastapi"]
    assert _taint(store, agent.handoff(sess.id)) == []


def test_the_source_list_is_capped(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([]))
    sess = store.create_session(str(repo), "main")
    for i in range(30):
        list(agent._note_taint(sess.id, {"name": "library_docs", "input": {"library": f"lib{i}"}}, False))
    assert len(_taint(store, sess.id)) == 20


# -- a tool call always gets a result, so a session never gets stuck ------------------------------------------------


def _answered(messages):
    """Every tool call in a request has its result: providers reject a conversation where one doesn't."""
    uses = {b["toolUse"]["toolUseId"] for m in messages for b in m["content"] if "toolUse" in b}
    results = {b["toolResult"]["toolUseId"] for m in messages for b in m["content"] if "toolResult" in b}
    return uses - results == set()


def test_a_github_call_with_an_unbalanced_quote_is_an_error_the_model_can_fix(cfg, store, repo, monkeypatch):
    from codepilot import github
    monkeypatch.setattr(github, "available", lambda: True)
    llm = FakeLLM([[tool_use("t1", "github", args='pr comment 5 --body "it\'s fine')], [{"text": "fixed the quoting"}],
                   [{"text": "ok"}]])
    agent = Agent(replace(cfg, github=True), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "comment on PR 5"))
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] and "quot" in result["output"]
    assert types(events)[-1] == "done" and len(llm.calls) == 2  # the turn went on, with the error in front of the model
    list(agent.chat(sess.id, "thanks"))
    assert _answered(llm.calls[-1]["messages"])


def test_an_unexpected_error_in_a_tool_becomes_its_result(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "list_files")], [{"text": "carrying on"}]])
    agent = Agent(cfg, store, llm=llm)

    def broken(ctx, **kwargs):
        raise RuntimeError("a bug in the tool")

    agent.tools["list_files"].fn = broken
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "list the files"))
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] and "a bug in the tool" in result["output"]
    assert types(events)[-1] == "done" and _answered(llm.calls[-1]["messages"])


def _interrupted(store, repo, *follow_ups):
    """A session as a restart mid-command leaves it: the call stored, its result never, maybe messages after it."""
    sess = store.create_session(str(repo), "main")
    store.add_message(sess.id, "user", [{"text": "run the long build"}])
    store.add_message(sess.id, "assistant", [{"text": "Building."}, tool_use("t1", "run_command", command="make all")])
    for text in follow_ups:  # stored before the provider rejected them
        store.add_message(sess.id, "user", [{"text": text}])
    return sess


def test_a_call_left_unanswered_by_a_restart_gets_a_result_before_the_next_message(cfg, store, repo):
    sess = _interrupted(store, repo)
    llm = FakeLLM([[{"text": "It didn't finish; shall I run it again?"}], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)  # a new process: the turn that made t1 is gone
    events = list(agent.chat(sess.id, "what happened?"))
    sent = llm.calls[0]["messages"]
    assert _answered(sent) and [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert "toolResult" in sent[2]["content"][0]  # results lead the message, as providers require
    # The card in the chat stops spinning: it gets its result, once, with one notice.
    assert [e["id"] for e in events if e["type"] == "tool_result"] == ["t1"]
    assert any(e["type"] == "notice" and "run_command" in e["message"] for e in events)
    events = list(agent.chat(sess.id, "run it again"))
    assert not any(e["type"] in ("tool_result", "notice") for e in events) and _answered(llm.calls[1]["messages"])


def test_a_session_stuck_with_messages_after_the_unanswered_call_recovers(cfg, store, repo):
    sess = _interrupted(store, repo, "hello?", "why does every message fail?")
    llm = FakeLLM([[{"text": "Back now."}]])
    events = list(Agent(cfg, store, llm=llm).chat(sess.id, "try again"))
    assert types(events)[-1] == "done" and _answered(llm.calls[0]["messages"])
    redrawn = [e for e in history_events(store, sess.id) if e["type"] == "user"]
    assert "mid" in redrawn[1] and redrawn[1]["text"] == "hello?"  # your messages stay ones you can edit or retry


def test_a_redrawn_session_shows_the_interrupted_call_as_not_run(cfg, store, repo):
    sess = _interrupted(store, repo)
    events = history_events(store, sess.id)
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["id"] == "t1" and result["is_error"] and "Not run" in result["output"]


def test_after_external_content_a_github_call_with_bad_quoting_is_an_error_not_an_approval(cfg, store, repo, monkeypatch):
    from codepilot import github
    monkeypatch.setattr(github, "available", lambda: True)
    llm = FakeLLM([[tool_use("t1", "github", args='issue comment 3 --body "it\'s fine')], [{"text": "fixed it"}]])
    agent = Agent(replace(cfg, github=True), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, context_state={"taint": [{"tool": "web_fetch", "detail": "fetch example.com"}]})
    events = list(agent.chat(sess.id, "comment on issue 3"))
    assert "approval_needed" not in types(events)
    assert next(e for e in events if e["type"] == "tool_result")["is_error"]


# -- a restart keeps each session's frozen system prompt ------------------------------------------------------------

ONE_TURN_IN_A_NEW_PROCESS = """
import json, sys
from dataclasses import replace
from pathlib import Path
from fakes import FakeLLM
from codepilot.agent import Agent
from codepilot.config import Config
from codepilot.store import Store

home, sid, text = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
cfg = replace(Config.from_env(), provider="bedrock", home=home, trace_dirs=[], log_groups=[], context_tokens=None)
llm = FakeLLM([[{"reasoningContent": {"reasoningText": {"text": "thinking", "signature": "sig-" + text}}},
                {"text": "ok"}]])
list(Agent(cfg, Store(home), llm=llm).chat(sid, text))
sent = llm.calls[0]
print(json.dumps({"system": sent["system"],
                  "reasoning": sum("reasoningContent" in b for m in sent["messages"] for b in m["content"])}))
"""


def test_a_restart_keeps_the_system_prompt_and_earlier_reasoning(cfg, store, repo):
    """Each turn runs in its own process, as after `make restart`. Python salts str hashes per process, so anything
    hash()-based in the prompt's key would rebuild the prompt (a cache miss) and strip every reasoning block."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, summary="SUMMARY: earlier work")  # compacted once, as long sessions are

    def turn(text, seed):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(Path(__file__).parent)}
        out = subprocess.run([sys.executable, "-c", ONE_TURN_IN_A_NEW_PROCESS, str(cfg.home), sess.id, text],
                             capture_output=True, text=True, env=env, cwd=repo, check=True).stdout
        return json.loads(out.strip().splitlines()[-1])

    first, second = turn("one", "1"), turn("two", "2")
    assert second["system"] == first["system"]
    assert second["reasoning"] == 1  # the first turn's reasoning is still there to replay


# -- a message that declines a waiting approval keeps what you attached ----------------------------------------------


def test_declining_an_approval_by_writing_keeps_your_attachments(cfg, store, repo):
    import base64

    from codepilot import images, mentions
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    llm = FakeLLM([[tool_use("t1", "run_command", command="make deploy")], [{"text": "Looking at the screenshot."}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    assert types(agent.chat(sess.id, "deploy it"))[-1] == "approval_needed"
    events = list(agent.chat(sess.id, "don't deploy; see this and @agent/core.py", pasted=[images.block(png)]))
    assert {"attached", "attached_images"} <= set(types(events))
    sent = llm.calls[-1]["messages"][-1]["content"]  # the decline and your message, as the model gets them
    assert sent[0]["toolResult"]["status"] == "error" and "declined" in sent[0]["toolResult"]["content"][0]["text"]
    assert any(b.get("text", "").startswith(mentions.ATTACH_OPEN) and "a - b" in b["text"] for b in sent)
    assert any("image" in b for b in sent)
    redrawn = types(history_events(store, sess.id))
    assert "attached" in redrawn and "attached_images" in redrawn


def test_stop_while_your_message_loads_its_attachments_stops_the_turn(cfg, store, repo, monkeypatch):
    from codepilot import images
    llm = FakeLLM([[tool_use("t1", "run_command", command="make deploy")],
                   [tool_use("t2", "list_files")], [{"text": "carried on"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "deploy it"))  # a command waits for approval

    def slow_link(text, root, added=()):  # an image link still downloading when you press Stop
        agent.cancel(sess.id)
        return [], []

    monkeypatch.setattr(images, "from_message", slow_link)
    events = list(agent.chat(sess.id, "no, see https://example.com/shot.png"))
    assert any(e["type"] == "notice" and e["message"] == "Stopped." for e in events)
    assert not any(e["type"] == "tool_call" for e in events)  # nothing ran after Stop


def test_history_draws_a_reply_in_the_order_it_streamed(store, repo):
    # Live, a reply's words stream before any of its tool calls is shown; a reopened session must keep that order.
    sess = store.create_session(str(repo), "main")
    store.add_message(sess.id, "user", [{"text": "look"}])
    store.add_message(sess.id, "assistant", [
        {"toolUse": {"toolUseId": "a", "name": "read_file", "input": {"path": "x.py"}}},
        {"text": "Now the other one."},
        {"toolUse": {"toolUseId": "b", "name": "read_file", "input": {"path": "y.py"}}}])
    shown = [e["type"] for e in history_events(store, sess.id) if e["type"] in ("assistant", "tool_call")]
    assert shown == ["assistant", "tool_call", "tool_call"]
