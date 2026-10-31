"""Steering docs: formats, inclusion modes, overrides, and how the agent loads them."""

import pytest
from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot import steering
from codepilot.agent import Agent, history_events
from codepilot.server import create_app

H = {"X-Codepilot": "1"}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def home(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "userhome"))  # keep the real ~/.kiro out of tests
    return cfg.home


def fm(front, body):
    return f"---\n{front}\n---\n{body}"


def by_name(docs):
    return {d.name: d for d in docs}


def test_formats_map_onto_inclusion_modes(repo, home):
    write(repo / ".codepilot/steering/style.md", "Use 4 spaces.\n")
    api = fm('inclusion: fileMatch\nfileMatchPattern: "agent/**/*.py"', "API rules")
    write(repo / ".codepilot/steering/api.md", api)
    write(repo / ".codepilot/steering/release.md", "---\ninclusion: manual\n---\nRelease checklist")
    write(repo / ".codepilot/steering/perf.md", fm("inclusion: auto\ndescription: Performance work", "Profile first"))
    write(repo / ".kiro/steering/tech.md", fm("inclusion: fileMatch\nfileMatchPattern:\n  - '*.ts'\n  - '*.tsx'", "TS"))
    write(repo / ".cursor/rules/always.mdc", "---\nalwaysApply: true\n---\nCursor always")
    write(repo / ".cursor/rules/react.mdc", "---\nglobs: src/**/*.tsx, src/**/*.jsx\n---\nReact")
    write(repo / ".cursor/rules/db.mdc", "---\ndescription: Database migrations\n---\nDB")
    write(repo / ".github/instructions/py.instructions.md", '---\napplyTo: "**/*.py"\n---\nCopilot py')
    write(repo / ".github/instructions/all.instructions.md", '---\napplyTo: "**"\n---\nCopilot all')
    write(repo / "CLAUDE.md", "Claude rules")
    docs = by_name(steering.discover(repo, home))
    assert docs["style"].inclusion == "always" and docs["style"].scope == "workspace"
    assert docs["api"].inclusion == "fileMatch" and docs["api"].patterns == ["agent/**/*.py"]
    assert docs["release"].inclusion == "manual" and docs["perf"].inclusion == "auto"
    assert docs["perf"].description == "Performance work"
    assert docs["tech"].patterns == ["*.ts", "*.tsx"] and docs["tech"].source == "kiro"
    assert docs["always"].inclusion == "always" and docs["react"].patterns == ["src/**/*.tsx", "src/**/*.jsx"]
    assert docs["db"].inclusion == "auto"
    assert docs["py"].inclusion == "fileMatch" and docs["all"].inclusion == "always"
    assert docs["CLAUDE"].inclusion == "always"


def test_workspace_overrides_global_with_the_same_name(repo, home):
    write(home / "steering/style.md", "Global style")
    write(home / "steering/security.md", "Never log secrets")
    write(repo / ".codepilot/steering/style.md", "Workspace style")
    docs = by_name(steering.discover(repo, home))
    assert docs["style"].body == "Workspace style" and docs["security"].scope == "global"
    text = steering.always_text(repo, home)
    assert "Workspace style" in text and "Global style" not in text and "Never log secrets" in text
    assert "Never log secrets" in steering.always_text(None, home)  # global docs apply with no folder open


def test_always_text_has_only_always_docs_and_expands_file_references(repo, home):
    write(repo / ".codepilot/steering/arch.md", "Follow the API spec:\n#[[file:docs/api.md]]\nSecret: #[[file:../x]]")
    write(repo / "docs/api.md", "GET /orders returns JSON")
    write(repo / ".codepilot/steering/later.md", "---\ninclusion: manual\n---\nManual only")
    text = steering.always_text(repo, home)
    assert "GET /orders returns JSON" in text and "Manual only" not in text
    assert "not found in the workspace" in text  # ../x is outside: never read


@pytest.mark.parametrize("rel,pattern,hit", [
    ("agent/core.py", "agent/**/*.py", True),
    ("agent/sub/deep/x.py", "agent/**/*.py", True),
    ("agent/core.py", "**/*.py", True),
    ("core.py", "**/*.py", True),
    ("web/app.tsx", "*.tsx", True),  # no slash: matches the file name anywhere
    ("web/app.ts", "*.tsx", False),
    ("src/a.jsx", "src/**/*.{tsx,jsx}", True),
    ("tests/test_x.py", "agent/**", False),
    (".github/workflows/ci.yml", ".github/**", True),
    ("api/v1.py", "./api/*.py", True),
])
def test_glob_matching(rel, pattern, hit):
    assert steering.glob_match(rel, pattern) is hit


def test_fingerprint_changes_when_docs_change(repo, home):
    before = steering.fingerprint(repo, home)
    write(repo / ".codepilot/steering/new.md", "New rule")
    assert steering.fingerprint(repo, home) != before


# -- the agent ----------------------------------------------------------------------------------------


def system_text(llm):
    return "\n".join(b["text"] for b in llm.calls[-1]["system"])


def test_always_docs_reach_the_model_and_edits_apply_next_turn(cfg, store, repo, home):
    doc = write(repo / ".codepilot/steering/style.md", "Prefer dataclasses.")
    llm = FakeLLM([[{"text": "a"}], [{"text": "b"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "hi"))
    assert "Prefer dataclasses." in system_text(llm)
    doc.write_text("Prefer attrs.")
    list(agent.chat(sess.id, "again"))
    assert "Prefer attrs." in system_text(llm) and "Prefer dataclasses." not in system_text(llm)


def test_file_match_doc_loads_once_when_a_matching_file_is_read(cfg, store, repo, home):
    write(repo / ".codepilot/steering/agent-rules.md",
          '---\ninclusion: fileMatch\nfileMatchPattern: "agent/**/*.py"\n---\nAgent code must log every call.')
    llm = FakeLLM([
        [tool_use("t1", "read_file", path="tests/test_core.py")],
        [tool_use("t2", "read_file", path="agent/core.py")],
        [tool_use("t3", "read_file", path="agent/core.py")],
        [{"text": "done"}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "look around"))
    assert "Agent code must log" not in system_text(llm)  # not always-on
    results = [b["toolResult"]["content"][0]["text"] for m in store.live_messages(sess.id) for b in m["content"]
               if "toolResult" in b]
    assert "Agent code must log" not in results[0]  # tests/ doesn't match
    assert "Agent code must log" in results[1] and "Agent code must log" not in results[2]  # once
    assert any(e["type"] == "steering" and e["names"] == ["agent-rules"] for e in events)


def test_manual_doc_attaches_when_named_with_hash(cfg, store, repo, home):
    write(repo / ".codepilot/steering/release.md", "---\ninclusion: manual\n---\nBump the version first.")
    llm = FakeLLM([[{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "prepare the release per #release please (see issue #42)"))
    sent = " ".join(b.get("text", "") for b in llm.calls[-1]["messages"][-1]["content"])
    assert "Bump the version first." in sent
    assert any(e["type"] == "steering" and e["names"] == ["release"] for e in events)
    replay = history_events(store, sess.id)  # reopening the session shows the chip, not the doc's text
    assert {"type": "steering", "names": ["release"]} in replay
    assert not any(e["type"] == "user" and "Bump the version" in e["text"] for e in replay)


def test_file_match_doc_loads_for_an_at_reference(cfg, store, repo, home):
    write(repo / ".codepilot/steering/core.md", fm('inclusion: fileMatch\nfileMatchPattern: "agent/*.py"', "CORE RULE"))
    llm = FakeLLM([[{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "review @agent/core.py"))
    assert "CORE RULE" in " ".join(b.get("text", "") for b in llm.calls[-1]["messages"][-1]["content"])


def test_auto_docs_are_listed_and_loadable(cfg, store, repo, home):
    write(repo / ".codepilot/steering/perf.md", fm("inclusion: auto\ndescription: Performance tuning", "PROFILE FIRST"))
    load = {"toolUse": {"toolUseId": "t1", "name": "load_skill", "input": {"name": "perf"}}}
    llm = FakeLLM([[load], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    list(agent.chat(sess.id, "speed this up"))
    assert "- perf: Performance tuning" in system_text(llm) and "PROFILE FIRST" not in system_text(llm)
    result = next(b["toolResult"]["content"][0]["text"] for m in store.live_messages(sess.id) for b in m["content"]
                  if "toolResult" in b)
    assert "PROFILE FIRST" in result


# -- endpoints ----------------------------------------------------------------------------------------


@pytest.fixture
def client(cfg, store, home):
    return TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))


def test_list_and_create_steering_docs(client, repo, home):
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    r = client.post(f"/api/sessions/{sid}/steering", json={"scope": "workspace", "name": "api-style",
                                                           "inclusion": "fileMatch", "pattern": "api/**"}, headers=H)
    assert r.json()["rel"] == ".codepilot/steering/api-style.md"
    assert 'fileMatchPattern: "api/**"' in (repo / ".codepilot/steering/api-style.md").read_text()
    assert client.post(f"/api/sessions/{sid}/steering", json={"scope": "workspace", "name": "api-style"},
                       headers=H).status_code == 409
    assert client.post(f"/api/sessions/{sid}/steering", json={"name": "../evil"}, headers=H).status_code == 400
    assert client.post(f"/api/sessions/{sid}/steering", json={"name": "x", "inclusion": "fileMatch"},
                       headers=H).status_code == 400  # needs a pattern
    assert client.post(f"/api/sessions/{sid}/steering", json={"scope": "global", "name": "security"},
                       headers=H).json()["scope"] == "global"
    docs = {d["name"]: d for d in client.get(f"/api/sessions/{sid}/steering").json()["docs"]}
    assert docs["api-style"]["inclusion"] == "fileMatch" and docs["api-style"]["rel"]
    assert docs["security"]["scope"] == "global" and docs["security"]["content"] and docs["security"]["editable"]


def test_global_doc_read_and_save_with_change_detection(client, home):
    write(home / "steering/security.md", "v1")
    got = client.get("/api/steering/global?name=security").json()
    assert got["content"] == "v1"
    assert client.put("/api/steering/global", json={"name": "security", "content": "v2", "base_mtime": got["mtime"]},
                      headers=H).status_code == 200
    stale = client.put("/api/steering/global", json={"name": "security", "content": "v3", "base_mtime": got["mtime"]},
                       headers=H)
    assert stale.status_code == 409 and (home / "steering/security.md").read_text() == "v2"
    assert client.get("/api/steering/global?name=../../etc/passwd").status_code == 400
    assert client.put("/api/steering/global", json={"name": "x", "content": "y"}).status_code == 403  # CSRF


# -- conventions-first /init and the cost of always-on steering ---------------------------------------


def test_conventions_prompt_asks_for_non_obvious_rules_with_evidence():
    p = steering.CONVENTIONS_PROMPT
    assert ".codepilot/steering/conventions.md" in p and "inclusion: always" in p
    assert "propose_edit" in p
    assert "25 lines" in p and "(see " in p  # a line cap, and each rule ends with where it comes from
    assert "overview" in p.lower()  # says not to write them, and why
    assert "additions" in p  # an existing conventions.md gets additions, not a replacement
    assert "nothing" in p.lower()  # and "nothing found" is an acceptable answer
    for old in ("product.md", "tech.md", "structure.md"):
        assert old not in p


def test_foundation_prompt_is_unchanged():
    p = steering.FOUNDATION_PROMPT
    assert all(f".codepilot/steering/{n}.md" in p for n in ("product", "tech", "structure"))
    assert "about 60 lines" in p and "conventions.md" not in p


def test_token_estimate_uses_the_context_meter_ratio():
    from codepilot import context
    assert steering.token_estimate("x" * 300) == round(300 * context.DEFAULT_TOKENS_PER_CHAR) == 100
    assert steering.token_estimate("") == 0


def test_info_has_tokens_only_for_always_on_docs(repo, home):
    write(repo / ".codepilot/steering/a.md", "x" * 300)
    write(repo / ".codepilot/steering/m.md", fm("inclusion: manual", "y" * 300))
    docs = {d.name: d.info(repo) for d in steering.discover(repo, home)}
    assert docs["a"]["tokens"] == 100
    assert docs["m"]["tokens"] is None


def test_list_endpoint_serves_the_prompts_and_the_always_on_total(client, repo, home):
    write(repo / ".codepilot/steering/a.md", "x" * 300)
    write(home / "steering/g.md", "z" * 600)
    write(repo / ".codepilot/steering/m.md", fm("inclusion: manual", "y" * 3000))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    d = client.get(f"/api/sessions/{sid}/steering").json()
    assert d["conventions_prompt"] == steering.CONVENTIONS_PROMPT
    assert d["foundation_prompt"] == steering.FOUNDATION_PROMPT
    assert d["always_tokens"] == 300  # 100 + 200; the manual doc isn't loaded every message
