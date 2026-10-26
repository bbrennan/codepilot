"""Messages typed while a turn runs (the queue), and editing or retrying earlier messages (rewind)."""

from fakes import FakeLLM, tool_use

from codepilot.agent import QUEUED_PREFIX, Agent, history_events


class QueueingLLM(FakeLLM):
    """Simulates the user typing while the model works: enqueue `text` during call number `at`."""

    def __init__(self, script, agent_ref, sid_ref, at, text):
        super().__init__(script)
        self.agent_ref, self.sid_ref, self.at, self.text = agent_ref, sid_ref, at, text

    def stream(self, model, system, messages, tools=None, max_tokens=None):
        if len([c for c in self.calls if "messages" in c]) == self.at:
            self.agent_ref[0].enqueue(self.sid_ref[0], self.text)
        yield from super().stream(model, system, messages, tools, max_tokens)


def make(cfg, store, repo, script, at, text):
    agent_ref, sid_ref = [None], [None]
    llm = QueueingLLM(script, agent_ref, sid_ref, at, text)
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    agent_ref[0], sid_ref[0] = agent, sess.id
    return agent, sess, llm


def last_user_text(call):
    return " ".join(b.get("text", "") for b in call["messages"][-1]["content"])


def test_message_queued_mid_turn_is_read_at_the_next_step(cfg, store, repo):
    agent, sess, llm = make(cfg, store, repo, [
        [tool_use("t1", "read_file", path="agent/core.py")],
        [{"text": "done, and used the other file"}],
    ], at=0, text="actually look at tests too")
    events = list(agent.chat(sess.id, "check add()"))
    second = [c for c in llm.calls if "messages" in c][1]
    assert QUEUED_PREFIX + "actually look at tests too" in last_user_text(second)
    user = [e for e in events if e["type"] == "user"]
    assert len(user) == 1 and user[0]["queued_id"]  # the UI swaps its "queued" bubble for this
    assert "mid" not in user[0]  # part of a running turn: not editable on its own (rewinding to it would fail)
    assert agent.queued(sess.id) == []
    replay = [e for e in history_events(store, sess.id) if e["type"] == "user"]
    assert replay[1] == {"type": "user", "text": "actually look at tests too", "queued": True}


def test_message_queued_during_the_final_reply_starts_the_next_turn(cfg, store, repo):
    agent, sess, llm = make(cfg, store, repo, [[{"text": "first answer"}], [{"text": "second answer"}]],
                            at=0, text="and one more thing")
    events = list(agent.chat(sess.id, "question"))
    types = [e["type"] for e in events]
    assert types.count("done") == 2 and types.count("turn") == 2
    follow = next(e for e in events if e["type"] == "user")
    assert follow["text"] == "and one more thing" and follow["queued_ids"]
    assert [m["role"] for m in store.live_messages(sess.id)] == ["user", "assistant", "user", "assistant"]


def test_stop_hands_queued_messages_back(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([]))
    sess = store.create_session(str(repo), "main")
    agent.enqueue(sess.id, "one")
    item = agent.enqueue(sess.id, "two")
    assert agent.dequeue(sess.id, item["id"]) and not agent.dequeue(sess.id, "nope")
    assert agent.cancel(sess.id) == ["one"] and agent.queued(sess.id) == []


def test_queued_messages_wait_while_approval_is_pending(cfg, store, repo):
    agent, sess, llm = make(cfg, store, repo, [[tool_use("t1", "run_command", command="ls")]], at=0, text="later")
    events = list(agent.chat(sess.id, "list files"))
    assert events[-1]["type"] == "approval_needed" and [q["text"] for q in agent.queued(sess.id)] == ["later"]


def test_edit_rewinds_and_resends(cfg, store, repo):
    llm = FakeLLM([[{"text": "a"}], [{"text": "b"}], [{"text": "c"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "first"))
    second_mid = next(e["mid"] for e in list(agent.chat(sess.id, "second")) if e["type"] == "turn")
    events = list(agent.rewind(sess.id, second_mid, "second, edited"))
    assert events[-1]["type"] == "done"
    texts = [(m["role"], m["content"][0].get("text")) for m in store.live_messages(sess.id)]
    assert texts == [("user", "first"), ("assistant", "a"), ("user", "second, edited"), ("assistant", "c")]
    assert [e.get("mid") for e in history_events(store, sess.id) if e["type"] == "user"][0] is not None


def test_rewind_refuses_tool_results_and_compacted_messages(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "read_file", path="agent/core.py")], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "read it"))
    msgs = store.messages(sess.id)
    results_mid = next(mid for mid, m in msgs if any("toolResult" in b for b in m["content"]))
    assert "Only a message that started a turn" in list(agent.rewind(sess.id, results_mid, "x"))[0]["message"]
    store.archive_messages(sess.id, [msgs[0][0]])
    assert "compacted" in list(agent.rewind(sess.id, msgs[0][0], "x"))[0]["message"]
    assert len(store.messages(sess.id)) == len(msgs) - 1  # nothing deleted


def test_run_after_messages_wait_for_the_turn_then_run_one_by_one(cfg, store, repo):
    agent, sess, llm = make(cfg, store, repo, [
        [tool_use("t1", "read_file", path="agent/core.py")], [{"text": "first done"}],
        [{"text": "second done"}], [{"text": "third done"}],
    ], at=0, text="steer: mention tests")
    agent.enqueue(sess.id, "then write docs", when="after")
    agent.enqueue(sess.id, "then tidy up", when="after")
    events = list(agent.chat(sess.id, "check add()"))
    calls = [c for c in llm.calls if "messages" in c]
    # The steering message joined the running turn at its next step; the "after" ones waited, then ran in order.
    assert "steer: mention tests" in last_user_text(calls[1]) and "then write docs" not in str(calls[1]["messages"])
    assert last_user_text(calls[2]).startswith("then write docs") and "then tidy up" not in last_user_text(calls[2])
    assert last_user_text(calls[3]).startswith("then tidy up")
    assert [e["text"] for e in events if e["type"] == "user" and e.get("queued_ids")] == ["then write docs",
                                                                                           "then tidy up"]


def test_a_waiting_message_can_switch_to_run_after(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([]))
    q = agent.enqueue("s1", "later please")
    assert agent.requeue("s1", q["id"], "after") and agent.queued("s1")[0]["when"] == "after"
    assert agent.take_queue("s1", "now") == [] and len(agent.queued("s1")) == 1
    assert not agent.requeue("s1", "nope", "now")
