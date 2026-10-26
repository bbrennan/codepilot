"""Auto model routing: the rules, and how the agent applies them per turn."""

from dataclasses import replace

import pytest
from fakes import FakeLLM, tool_use

from codepilot import router
from codepilot.agent import Agent


@pytest.mark.parametrize("mode,text,last,tier", [
    ("build", "rename this variable", None, "main"),
    ("build", "please think hard about why this deadlocks", None, "hard"),
    ("build", "ultrathink: fix the cache", None, "hard"),
    ("plan", "add CSV export", None, "hard"),
    ("debug", "the total is wrong", None, "hard"),
    ("bughunt", "look for bugs in billing", None, "hard"),
    ("ask", "what does add() do?", None, "fast"),
    ("ask", "explain " + "x " * 400, None, "main"),
    ("build", "refactor the billing module into services", None, "hard"),
    ("build", "update @a.py @b.py @c.py to use the new client", None, "hard"),
    ("build", "x" * 1600, None, "hard"),
    ("build", "continue", {"failures": 2}, "hard"),
    ("build", "continue", {"hit_limit": True}, "hard"),
    ("build", "continue", {"failures": 1}, "main"),
])
def test_rules(mode, text, last, tier):
    assert router.choose(mode, text, last).tier == tier


def test_failed_run_detection():
    assert router.failed_run("run_tests", "exit code 1\nFAILED test_x", False)
    assert not router.failed_run("run_tests", "exit code 0\n3 passed", False)
    assert router.failed_run("run_command", "timed out", True)
    assert not router.failed_run("read_file", "exit code 1", False)


def models_used(llm):
    return [c["model"] for c in llm.calls if "model" in c]


def test_auto_picks_per_turn_and_says_why(cfg, store, repo):
    llm = FakeLLM([[{"text": "a"}], [{"text": "b"}], [{"text": "c"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "auto")
    events = list(agent.chat(sess.id, "rename a variable"))
    route = next(e for e in events if e["type"] == "route")
    assert route["tier"] == "main" and route["model"] == cfg.models["main"] and route["reason"] == "routine work"
    list(agent.chat(sess.id, "think hard: why is this slow?"))
    store.update_session(sess.id, mode="ask")
    list(agent.chat(sess.id, "what is add?"))
    assert models_used(llm) == [cfg.models["main"], cfg.models["hard"], cfg.models["fast"]]


def test_fixed_tier_and_pinned_model_are_respected(cfg, store, repo):
    llm = FakeLLM([[{"text": "a"}], [{"text": "b"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "fast")
    events = list(agent.chat(sess.id, "think hard about everything"))
    assert not any(e["type"] == "route" for e in events) and models_used(llm) == [cfg.models["fast"]]
    store.update_session(sess.id, tier="auto", model="anthropic.claude-opus-4-8")
    list(agent.chat(sess.id, "rename it"))
    assert models_used(llm)[-1] == "anthropic.claude-opus-4-8"


def test_failing_runs_get_a_second_opinion_then_the_next_turn_escalates(cfg, store, repo):
    cfg = replace(cfg, test_cmd="python -c \"import sys; print('1 failed'); sys.exit(1)\"")
    llm = FakeLLM([
        [tool_use("t1", "run_tests")],
        [tool_use("t2", "run_tests")],
        [{"text": "still failing"}],
        [{"text": "next turn"}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "auto", auto_approve=True)
    events = list(agent.chat(sess.id, "fix the tests"))
    advisor = [e for e in events if e["type"] == "advisor"]
    assert len(advisor) == 1 and advisor[0]["model"] == cfg.models["hard"]  # once, after the second failure
    results = [b["toolResult"]["content"][0]["text"] for m in store.live_messages(sess.id) for b in m["content"]
               if "toolResult" in b]
    assert "<advisor" not in results[0] and "<advisor" in results[1]
    assert any("complete" in c for c in llm.calls)
    events = list(agent.chat(sess.id, "continue"))
    route = next(e for e in events if e["type"] == "route")
    assert route["tier"] == "hard" and "2 failing runs" in route["reason"]


def test_switching_models_drops_the_old_models_reasoning(cfg, store, repo):
    reasoning = {"reasoningContent": {"reasoningText": {"text": "hmm", "signature": "sig"}}}
    llm = FakeLLM([[reasoning, {"text": "a"}], [{"text": "b"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "auto")
    list(agent.chat(sess.id, "think hard about this"))
    assert any("reasoningContent" in b for m in store.live_messages(sess.id) for b in m["content"])
    list(agent.chat(sess.id, "rename a variable"))  # hard -> main
    assert not any("reasoningContent" in b for m in store.live_messages(sess.id) for b in m["content"])


def test_auto_uses_the_newest_available_sonnet_by_default(cfg, store, repo):
    from codepilot import models

    cfg = replace(cfg, models={"fast": "anthropic.claude-haiku-4-5", "main": "anthropic.claude-sonnet-4-5",
                               "hard": "anthropic.claude-opus-4-7"})
    available = ["anthropic.claude-sonnet-4-5", "anthropic.claude-sonnet-5", "anthropic.claude-sonnet-5-5",
                 "anthropic.claude-opus-5-5", "anthropic.claude-haiku-4-5"]
    models.discover(cfg, refresh=True, lister=lambda _c: available + ["anthropic.claude-haiku-5-5"],
                    probe=lambda _c, m: (m in available, "ok" if m in available else "pending onboarding"))
    llm = FakeLLM([[{"text": "a"}], [{"text": "b"}], [{"text": "c"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "auto")
    list(agent.chat(sess.id, "rename a variable"))
    list(agent.chat(sess.id, "think hard about it"))
    store.update_session(sess.id, mode="ask")
    list(agent.chat(sess.id, "what is add?"))
    # newest Sonnet, newest Opus, and Haiku 4.5 because 5.5 isn't enabled yet
    assert models_used(llm) == ["anthropic.claude-sonnet-5-5", "anthropic.claude-opus-5-5",
                                "anthropic.claude-haiku-4-5"]
    store.update_session(sess.id, tier="main", mode="build")  # a fixed tier also uses the newest of its family
    llm.script.append([{"text": "d"}])
    list(agent.chat(sess.id, "rename"))
    assert models_used(llm)[-1] == "anthropic.claude-sonnet-5-5"
    pinned = Agent(replace(cfg, latest_models=False), store, llm=llm)  # CODEPILOT_LATEST_MODELS=0: as configured
    llm.script += [[{"text": "e"}], [{"text": "f"}]]
    list(pinned.chat(sess.id, "rename"))
    store.update_session(sess.id, tier="auto")
    list(pinned.chat(sess.id, "rename it back"))
    assert models_used(llm)[-2:] == ["anthropic.claude-sonnet-4-5", "anthropic.claude-sonnet-4-5"]
