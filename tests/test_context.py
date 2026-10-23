import json
from dataclasses import replace

import pytest
from conftest import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot.agent import Agent
from codepilot.bedrock import BedrockError
from codepilot.context import CLEARED_PREFIX, is_overflow
from codepilot.server import create_app


class RealisticLLM(FakeLLM):
    """Reports prompt tokens as ~1 per 3 characters sent, like a real model would."""

    def __init__(self, script, fail_on=()):
        super().__init__(script)
        self.fail_on = set(fail_on)

    def stream(self, model, system, messages, tools=None, max_tokens=None):
        n = len(self.calls)
        self.calls.append({"model": model, "system": system, "messages": json.loads(json.dumps(messages)),
                           "tools": tools})
        if n in self.fail_on:
            raise BedrockError("Bedrock rejected the request: Input is too long for requested model.")
        content = self.script.pop(0)
        for b in content:
            if "text" in b:
                yield {"type": "text", "text": b["text"]}
        sent = len(json.dumps(system)) + len(json.dumps(tools or [])) + len(json.dumps(messages))
        yield {"type": "message", "content": content,
               "stop_reason": "tool_use" if any("toolUse" in b for b in content) else "end_turn",
               "usage": {"inputTokens": sent // 3, "outputTokens": 50}}


def big_repo(repo):
    (repo / "big.py").write_text("".join(f"value_{i} = 'x' * {i}  # padding padding padding\n" for i in range(600)))
    return repo


def test_context_window_defaults(cfg):
    assert replace(cfg, provider="bedrock").context_window("us.anthropic.claude-sonnet-4-5-x") == 200_000
    assert replace(cfg, provider="anthropic").context_window("claude-sonnet-5-5") == 1_000_000
    assert replace(cfg, provider="anthropic").context_window("claude-haiku-4-5") == 200_000
    assert replace(cfg, provider="ollama", ollama_num_ctx=8192).context_window("x") == 8192
    assert replace(cfg, context_tokens=50_000).context_window("anything") == 50_000


@pytest.mark.parametrize("msg,hit", [
    ("ValidationException: Input is too long for requested model.", True),
    ("prompt is too long: 210000 tokens > 200000 maximum", True),
    ("This model's maximum context length is 128000 tokens", True),
    ("input length and `max_tokens` exceed context limit", True),
    ("AccessDeniedException: no access", False), ("rate limit hit", False),
])
def test_overflow_detection(msg, hit):
    assert is_overflow(msg) is hit


def test_prunes_old_tool_outputs_mid_task(cfg, store, repo):
    cfg = replace(cfg, context_tokens=40_000, max_tokens=4000, max_steps=12)
    big_repo(repo)
    script = [[tool_use(f"r{i}", "read_file", path="big.py", start_line=1, end_line=500)] for i in range(6)]
    llm = RealisticLLM(script + [[{"text": "done reading"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "read big.py a few times"))
    assert events[-1]["type"] == "done" and not [e for e in events if e["type"] == "error"]
    assert any(e["type"] == "notice" and e["message"].startswith("Freed ~") for e in events)
    results = [b["toolResult"] for m in store.live_messages(sess.id) for b in m["content"] if "toolResult" in b]
    texts = [r["content"][0]["text"] for r in results]
    assert texts[0].startswith(CLEARED_PREFIX) and "read_file" in texts[0]   # oldest cleared
    assert not texts[-1].startswith(CLEARED_PREFIX)                          # recent kept verbatim
    # The request that followed the pruning fit comfortably in the budget.
    last = llm.calls[-1]
    sent = len(json.dumps(last["system"])) + len(json.dumps(last["tools"])) + len(json.dumps(last["messages"]))
    assert sent // 3 < agent.ctxm.budget(cfg.models["main"])


def test_summarises_earlier_turns_with_exact_working_state(cfg, store, repo):
    # Pruning alone would keep this session small, so trigger summarising first to exercise tier 2.
    cfg = replace(cfg, context_tokens=24_000, max_tokens=2000, prune_at=0.95, compact_at=0.5)
    big_repo(repo)
    plan = [{"text": "read the code", "status": "done"}, {"text": "fix it", "status": "doing"}]
    script = []
    for i in range(5):
        script += [[tool_use(f"p{i}", "update_plan", items=plan), tool_use(f"r{i}", "read_file", path="big.py")],
                   [{"text": f"answer {i} " + "detail " * 400}]]
    llm = RealisticLLM(script)
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    for i in range(5):
        events = list(agent.chat(sess.id, f"question {i}"))
        assert not [e for e in events if e["type"] == "error"], events
    s = store.get_session(sess.id)
    assert s.summary.startswith("SUMMARY: earlier work")
    assert "Working state (exact" in s.summary and "[x] read the code; [>] fix it" in s.summary
    assert "big.py" in s.summary
    live = store.live_messages(sess.id)
    assert live[0]["role"] == "user" and live[0]["content"][0]["text"].startswith("question")
    assert any("SUMMARY: earlier work" in b["text"] for b in llm.calls[-1]["system"])


def test_overflow_error_recovers_by_compacting(cfg, store, repo):
    llm = RealisticLLM([[{"text": "one " * 50}], [{"text": "two " * 50}], [{"text": "recovered"}]], fail_on={2})
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "first"))
    list(agent.chat(sess.id, "second"))
    events = list(agent.chat(sess.id, "third"))
    assert any(e["type"] == "notice" and "Compacting and retrying" in e["message"] for e in events)
    assert any(e.get("text") == "recovered" for e in events)
    assert not [e for e in events if e["type"] == "error"]
    assert store.get_session(sess.id).summary


def test_overflow_with_nothing_to_compact_reports_clearly(cfg, store, repo):
    llm = RealisticLLM([], fail_on={0, 1})
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "huge first message"))
    err = next(e for e in events if e["type"] == "error")
    assert "/compact" in err["message"] and "Continue in new session" in err["message"]


def test_compact_slash_command_with_focus(cfg, store, repo):
    llm = RealisticLLM([[{"text": "a"}], [{"text": "b"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "first"))
    list(agent.chat(sess.id, "second"))
    events = list(agent.chat(sess.id, "/compact the API changes"))
    assert [e["type"] for e in events][-2:] == ["context", "done"]
    assert "Focus requested by the user: the API changes" in llm.calls[-1]["complete"]
    assert store.live_messages(sess.id) == [] and store.get_session(sess.id).summary
    assert len(llm.script) == 0 and len([c for c in llm.calls if "messages" in c]) == 2  # no main-model call


def test_handoff_and_compact_endpoints(cfg, store, repo):
    llm = RealisticLLM([[{"text": "hello"}]])
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=llm)))
    H = {"X-Codepilot": "1"}
    sess = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()
    client.post(f"/api/sessions/{sess['id']}/chat", json={"message": "hi"}, headers=H)
    ctx = client.get(f"/api/sessions/{sess['id']}").json()["context"]
    assert ctx["budget"] == 200_000 - 16_000 and ctx["tokens"] > 0
    new = client.post(f"/api/sessions/{sess['id']}/handoff", headers=H).json()
    assert new["id"] != sess["id"] and new["repo"] == str(repo.resolve()) and new["has_summary"]
    out = client.post(f"/api/sessions/{new['id']}/compact", json={"focus": ""}, headers=H).text
    assert '"type": "done"' in out
