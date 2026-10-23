from codepilot import mentions
from codepilot.agent import Agent, history_events
from fakes import FakeLLM


def test_attachment_block_files_ranges_and_dirs(repo):
    root = repo.resolve()
    text = "Why does @agent/core.py:2 subtract? Compare with @tests/test_core.py, and see @agent. Ignore @nowhere.py"
    block, labels = mentions.attachment_block(root, text)
    assert labels == ["agent/core.py:2-2", "tests/test_core.py", "agent"]
    assert '<file path="agent/core.py" lines="2-2">\n    2      return a - b\n</file>' in block
    assert '<directory path="agent">\ncore.py\n</directory>' in block
    assert "nowhere" not in block
    assert mentions.attached_labels(block) == ["agent/core.py:2-2", "tests/test_core.py", "agent"]


def test_mentions_stay_inside_workspace(repo, tmp_path):
    (tmp_path / "secret.txt").write_text("s3cret")
    block, labels = mentions.attachment_block(repo.resolve(), "read @../secret.txt and @/etc/hosts")
    assert block == "" and labels == []
    # e-mail addresses and code spans are not mentions
    assert mentions.find_mentions(repo.resolve(), "mail me@agent/core.py or `@agent/core.py`") == []


def test_find_files_fuzzy(repo):
    root = repo.resolve()
    assert mentions.find_files(root, "core")[0] == "agent/core.py"
    assert "tests/test_core.py" in mentions.find_files(root, "tstcore")
    assert mentions.find_files(root, "zzzz") == []


def test_chat_attaches_and_replays(cfg, store, repo):
    llm = FakeLLM([[{"text": "It subtracts."}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "explain @agent/core.py"))
    assert events[0] == {"type": "attached", "paths": ["agent/core.py"]}
    sent = llm.calls[0]["messages"][0]["content"]
    assert sent[0]["text"] == "explain @agent/core.py" and "return a - b" in sent[1]["text"]
    ctx = next(e for e in events if e["type"] == "context")
    assert 0 < ctx["tokens"] < ctx["budget"]
    replay = history_events(store, sess.id)
    assert replay[:2] == [{"type": "user", "text": "explain @agent/core.py", "mid": 1},
                          {"type": "attached", "paths": ["agent/core.py"]}]
