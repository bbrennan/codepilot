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
