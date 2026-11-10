import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot.agent import Agent
from codepilot.server import create_app

H = {"X-Codepilot": "1"}


@pytest.fixture
def client_and_llm(cfg, store):
    llm = FakeLLM([
        [tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b", reason="fix")],
        [{"text": "Proposed a fix."}],
    ])
    app = create_app(cfg, store, Agent(cfg, store, llm=llm))
    return TestClient(app), llm


def ndjson(resp):
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_full_flow(client_and_llm, repo):
    client, _ = client_and_llm
    assert client.get("/").status_code == 200
    assert client.get("/api/config").json()["provider"] == "bedrock"

    sess = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()
    events = ndjson(client.post(f"/api/sessions/{sess['id']}/chat", json={"message": "fix add"}, headers=H))
    prop = next(e for e in events if e["type"] == "proposal")["proposal"]
    assert events[-1]["type"] == "done"

    detail = client.get(f"/api/sessions/{sess['id']}").json()
    assert [e["type"] for e in detail["events"]][:2] == ["user", "tool_call"]
    assert detail["proposals"][0]["status"] == "pending"

    r = client.post(f"/api/proposals/{prop['id']}/apply", headers=H)
    assert r.json()["status"] == "applied"
    assert "a + b" in (repo / "agent/core.py").read_text()
    assert client.post(f"/api/proposals/{prop['id']}/apply", headers=H).status_code == 400
    undone = client.post(f"/api/proposals/{prop['id']}/revert", headers=H).json()
    assert undone["status"] == "reverted" and "a - b" in (repo / "agent/core.py").read_text()
    assert client.post(f"/api/proposals/{prop['id']}/revert", headers=H).status_code == 409
    patched = client.patch(f"/api/sessions/{sess['id']}", json={"mode": "plan"}, headers=H).json()
    assert patched["session"]["mode"] == "plan"
    assert client.patch(f"/api/sessions/{sess['id']}", json={"mode": "yolo"}, headers=H).status_code == 400

    traces = client.get(f"/api/sessions/{sess['id']}/traces").json()
    assert {f["path"] for f in traces["files"]} == {"traces/journey_1.json", "traces/run.jsonl"}
    view = client.get(f"/api/sessions/{sess['id']}/trace", params={"path": "traces/journey_1.json"}).json()
    assert view["outline"]["errors"] == 1 and view["records"][0]["journey"] == "j1"

    files = client.get(f"/api/sessions/{sess['id']}/files", params={"path": "agent"}).json()
    assert files["entries"][0]["name"] == "core.py"
    assert client.get(f"/api/sessions/{sess['id']}/files", params={"path": "../.."}).status_code == 404

    run = client.post(f"/api/sessions/{sess['id']}/run", json={"kind": "tests"}, headers=H).json()
    assert run["ok"] and "tests-ran" in run["output"]
    run = client.post(f"/api/sessions/{sess['id']}/run", json={"kind": "command", "command": "exit 3"},
                      headers=H).json()
    assert not run["ok"] and "exit code 3" in run["output"]

    found = client.get(f"/api/sessions/{sess['id']}/find", params={"q": "core"}).json()["files"]
    assert found[0] == "agent/core.py"
    assert "context" in client.get(f"/api/sessions/{sess['id']}").json()

    ws = client.get(f"/api/sessions/{sess['id']}/workspace").json()
    assert "code-review" in {s["name"] for s in ws["skills"]}

    notes = client.put(f"/api/sessions/{sess['id']}/notes", json={"notes": "- uses uv\n"}, headers=H).json()
    assert notes["notes"] == "- uses uv\n"


def test_post_without_header_is_rejected(client_and_llm, repo):
    client, _ = client_and_llm
    assert client.post("/api/sessions", json={"repo": str(repo)}).status_code == 403


def test_foreign_host_is_rejected(client_and_llm):
    client, _ = client_and_llm
    assert client.get("/api/config", headers={"Host": "evil.example"}).status_code == 400


def test_open_folder_grep_and_cancel(client_and_llm, repo):
    client, _ = client_and_llm
    sess = client.post("/api/sessions", json={}, headers=H).json()
    r = client.patch(f"/api/sessions/{sess['id']}", json={"repo": str(repo)}, headers=H).json()
    assert r["session"]["repo"] == str(repo.resolve())
    assert client.patch(f"/api/sessions/{sess['id']}", json={"repo": "/nope/nope"}, headers=H).status_code == 400
    hits = client.get(f"/api/sessions/{sess['id']}/grep", params={"q": "return a - b"}).json()["results"]
    assert hits == [{"path": "agent/core.py", "line": 2, "text": "    return a - b"}]
    assert client.get(f"/api/sessions/{sess['id']}/grep", params={"q": "add(("}).status_code == 200  # bad regex ok
    assert client.post(f"/api/sessions/{sess['id']}/cancel", headers=H).json() == {"ok": True, "queued": []}
    listed = client.get("/api/sessions").json()
    assert listed[0]["busy"] is False
    assert client.get("/static/app.js").status_code == 200


def test_session_without_workspace(client_and_llm):
    client, _ = client_and_llm
    sess = client.post("/api/sessions", json={}, headers=H).json()
    assert sess["repo"] == ""
    assert client.get(f"/api/sessions/{sess['id']}/files").status_code == 409
    assert client.get(f"/api/sessions/{sess['id']}").status_code == 200


def test_bad_repo(client_and_llm, tmp_path):
    client, _ = client_and_llm
    r = client.post("/api/sessions", json={"repo": str(tmp_path / "nope")}, headers=H)
    assert r.status_code == 400 and "Not a directory" in r.json()["error"]


def test_browse_folders(client_and_llm, repo):
    client, _ = client_and_llm
    d = client.get("/api/browse", params={"path": str(repo)}).json()
    assert d["path"] == str(repo.resolve()) and d["project"] == "make"  # Makefile marker (git checked later)
    assert {x["name"] for x in d["dirs"]} == {"agent", "tests", "traces"}  # .git hidden
    assert d["places"][0]["name"] == "Home"
    hidden = client.get("/api/browse", params={"path": str(repo), "hidden": "1"}).json()
    assert ".git" in {x["name"] for x in hidden["dirs"]}
    assert client.get("/api/browse", params={"path": str(repo / "nope")}).status_code == 404
    assert client.get("/api/browse").json()["path"] == str(Path.home())


def _token(client):
    import re

    return re.search(r'name="codepilot-token" content="([^"]*)"', client.get("/").text).group(1)


def test_terminal_round_trip(client_and_llm, repo):
    from starlette.websockets import WebSocketDisconnect

    client, _ = client_and_llm
    sess = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()
    token = _token(client)
    assert len(token) > 30
    origin = {"origin": "http://testserver"}
    with client.websocket_connect(f"/api/terminal?token={token}&sid={sess['id']}", headers=origin) as ws:
        ws.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        ws.send_text(json.dumps({"type": "input", "data": "pwd; echo cp-term-$((40+2))\n"}))
        seen = ""
        for _ in range(200):
            seen += ws.receive_text()
            if "cp-term-42" in seen:
                break
        assert "cp-term-42" in seen
        assert str(repo.resolve()).removeprefix("/private") in seen.replace("/private", "")
        ws.send_text(json.dumps({"type": "input", "data": "exit\n"}))
    for bad_query, headers in ((f"token=wrong&sid={sess['id']}", origin),
                               (f"token={token}", {"origin": "http://evil.example"}),
                               (f"token={token}", {})):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/terminal?{bad_query}", headers=headers) as ws:
                ws.receive_text()


def test_terminal_disabled(cfg, store):
    from dataclasses import replace

    from starlette.websockets import WebSocketDisconnect

    client = TestClient(create_app(replace(cfg, terminal=False), store, Agent(cfg, store, llm=FakeLLM([]))))
    assert _token(client) == ""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/terminal?token=", headers={"origin": "http://testserver"}) as ws:
            ws.receive_text()


def test_saved_proposals_have_full_context_diffs(client_and_llm, repo):
    client, _ = client_and_llm
    sess = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()
    ndjson(client.post(f"/api/sessions/{sess['id']}/chat", json={"message": "fix add"}, headers=H))
    pending = client.get(f"/api/sessions/{sess['id']}").json()["proposals"][0]
    assert " def add(a, b):" in pending["diff"]  # context line from the real file, not just the snippet
    applied = client.post(f"/api/proposals/{pending['id']}/apply", headers=H).json()
    assert " def add(a, b):" in applied["diff"] and "+    return a + b" in applied["diff"]


def test_git_branch_before_the_first_commit(client_and_llm, repo):
    client, _ = client_and_llm
    sess = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()
    g = client.get(f"/api/sessions/{sess['id']}/git").json()
    assert g["git"] and g["branch"] and "fatal" not in g["branch"]  # fresh `git init`, no commits yet


def test_a_turn_keeps_running_when_the_page_goes_away_and_can_be_followed(cfg, store, repo):
    import threading
    import time

    gate = threading.Event()

    class SlowLLM(FakeLLM):
        def stream(self, model, system, messages, tools=None, max_tokens=None):
            gate.wait(10)
            yield from super().stream(model, system, messages, tools, max_tokens)

    agent = Agent(cfg, store, llm=SlowLLM([[{"text": "finished anyway"}]]))
    client = TestClient(create_app(cfg, store, agent))
    hdr = {"X-Codepilot": "1"}
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=hdr).json()["id"]
    with client.stream("POST", f"/api/sessions/{sid}/chat", json={"message": "hi"}, headers=hdr) as r:
        next(r.iter_lines())  # the page reads a little, then is reloaded
    assert client.get(f"/api/sessions/{sid}").json()["busy"] is True
    with client.stream("GET", f"/api/sessions/{sid}/follow", headers=hdr) as r:
        gate.set()
        lines = [ln for ln in r.iter_lines() if ln.strip()]
    assert any("finished anyway" in ln for ln in lines) and '"done"' in lines[-1]
    for _ in range(50):
        if not client.get(f"/api/sessions/{sid}").json()["busy"]:
            break
        time.sleep(0.05)
    assert client.get(f"/api/sessions/{sid}/follow", headers=hdr).status_code == 204
    assert any("finished anyway" in str(m) for m in store.live_messages(sid))


def test_a_message_queued_as_the_stream_ends_still_runs(cfg, store, repo, monkeypatch):
    agent = Agent(cfg, store, llm=FakeLLM([[{"text": "one"}], [{"text": "two"}]]))
    real_chat = agent.chat

    def chat_then_late_queue(sid, text, tier=None, pasted=None):
        yield from real_chat(sid, text, tier, pasted)
        agent.enqueue(sid, "late arrival", when="after")  # after the agent's own last check of the queue

    monkeypatch.setattr(agent, "chat", chat_then_late_queue)
    client = TestClient(create_app(cfg, store, agent))
    hdr = {"X-Codepilot": "1"}
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=hdr).json()["id"]
    lines = client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"}, headers=hdr).text.splitlines()
    assert any("late arrival" in ln for ln in lines) and any('"two"' in ln for ln in lines)


def test_a_message_sent_while_working_queues_unless_it_asks_to_steer(cfg, store, repo):
    import threading

    gate = threading.Event()

    class SlowLLM(FakeLLM):
        def stream(self, model, system, messages, tools=None, max_tokens=None):
            gate.wait(10)
            yield from super().stream(model, system, messages, tools, max_tokens)

    agent = Agent(cfg, store, llm=SlowLLM([[{"text": "done"}]]))
    client = TestClient(create_app(cfg, store, agent))
    hdr = {"X-Codepilot": "1"}
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=hdr).json()["id"]
    with client.stream("POST", f"/api/sessions/{sid}/chat", json={"message": "hi"}, headers=hdr) as r:
        next(r.iter_lines())
        assert client.post(f"/api/sessions/{sid}/queue", json={"text": "later"}, headers=hdr).json()["when"] == "after"
        steer = client.post(f"/api/sessions/{sid}/queue", json={"text": "now", "when": "now"}, headers=hdr).json()
        assert steer["when"] == "now"
        assert [q["text"] for q in client.get(f"/api/sessions/{sid}/queue").json()["queued"]] == ["later", "now"]
        client.post(f"/api/sessions/{sid}/cancel", headers=hdr)
        gate.set()


def test_stat_reports_folder_and_file_changes(cfg, store, repo):
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    hdr = {"X-Codepilot": "1"}
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=hdr).json()["id"]
    body = {"dirs": [".", "agent", "gone", "../.."], "files": ["agent/core.py", "nope.py"]}
    first = client.post(f"/api/sessions/{sid}/stat", json=body, headers=hdr).json()
    assert first["dirs"]["gone"] is None and first["dirs"]["../.."] is None and first["files"]["nope.py"] is None
    assert first["dirs"]["agent"] == client.get(f"/api/sessions/{sid}/files", params={"path": "agent"}).json()["stamp"]
    (repo / "agent" / "new.py").write_text("")
    (repo / "agent" / "core.py").write_text("changed = True\n")
    second = client.post(f"/api/sessions/{sid}/stat", json=body, headers=hdr).json()
    assert second["dirs"]["agent"] != first["dirs"]["agent"] and second["dirs"]["."] == first["dirs"]["."]
    assert second["files"]["agent/core.py"] != first["files"]["agent/core.py"]


def _auto_applied(cfg, store, repo, llm=None):
    """A session whose first turn auto-applied a fix to agent/core.py; returns (client, sid, mid of that turn)."""
    llm = llm or FakeLLM([[tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
                          [{"text": "fixed"}], [{"text": "again"}]])
    client = TestClient(create_app(replace(cfg, auto_apply_edits=True), store,
                                   Agent(replace(cfg, auto_apply_edits=True), store, llm=llm)))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    ndjson(client.post(f"/api/sessions/{sid}/chat", json={"message": "fix add"}, headers=H))
    mid = next(e["mid"] for e in client.get(f"/api/sessions/{sid}").json()["events"] if e["type"] == "user")
    return client, sid, mid


def test_checkpoint_lists_a_turns_changes_and_restore_undoes_them(cfg, store, repo):
    original = (repo / "agent/core.py").read_text()
    client, sid, mid = _auto_applied(cfg, store, repo)
    assert "a + b" in (repo / "agent/core.py").read_text()
    preview = client.get(f"/api/sessions/{sid}/checkpoint?mid={mid}").json()
    assert preview == {"changes": [{"id": 1, "path": "agent/core.py", "ok": True, "reason": ""}]}
    r = client.post(f"/api/sessions/{sid}/restore", json={"ids": [1]}, headers=H).json()
    assert [p["status"] for p in r["reverted"]] == ["reverted"] and r["left"] == []
    assert r["message"] == "Undid 1 file change (agent/core.py)."
    assert (repo / "agent/core.py").read_text() == original
    assert client.get(f"/api/sessions/{sid}/checkpoint?mid={mid}").json() == {"changes": []}
    assert len(store.messages(sid)) == 4  # the conversation is untouched


def test_checkpoint_and_restore_reject_bad_input(cfg, store, repo):
    client, sid, _ = _auto_applied(cfg, store, repo)
    assert client.get(f"/api/sessions/{sid}/checkpoint?mid=x").status_code == 400
    assert client.get("/api/sessions/nope/checkpoint?mid=1").status_code == 404
    assert client.post(f"/api/sessions/{sid}/restore", json={"ids": "1"}, headers=H).status_code == 400
    assert client.post(f"/api/sessions/{sid}/rewind", json={"mid": 1, "message": "x", "restore": ["a"]},
                       headers=H).status_code == 400


def test_rewind_with_restore_undoes_the_changes_first(cfg, store, repo):
    original = (repo / "agent/core.py").read_text()
    client, sid, mid = _auto_applied(cfg, store, repo)
    events = ndjson(client.post(f"/api/sessions/{sid}/rewind", json={"mid": mid, "message": "fix add, again",
                                                                    "restore": [1]}, headers=H))
    assert any(e["type"] == "notice" and e["message"].startswith("Undid 1 file change") for e in events)
    assert (repo / "agent/core.py").read_text() == original and events[-1]["type"] == "done"


def test_restore_waits_while_the_session_is_working(cfg, store, repo):
    gate = threading.Event()

    class GatedLLM(FakeLLM):
        def stream(self, model, system, messages, tools=None, max_tokens=None):
            if len(self.calls) >= 2:
                gate.wait(10)
            yield from super().stream(model, system, messages, tools, max_tokens)

    llm = GatedLLM([[tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
                    [{"text": "fixed"}], [{"text": "slow"}]])
    client, sid, _ = _auto_applied(cfg, store, repo, llm)
    with client.stream("POST", f"/api/sessions/{sid}/chat", json={"message": "more"}, headers=H) as r:
        next(r.iter_lines())
        busy = client.post(f"/api/sessions/{sid}/restore", json={"ids": [1]}, headers=H)
        gate.set()
    assert busy.status_code == 409 and "already working" in busy.json()["error"]
    assert store.get_proposal(1).status == "applied"


def test_restore_reports_a_partial_failure(cfg, store, repo):
    client, sid, _ = _auto_applied(cfg, store, repo)
    (repo / "agent/core.py").chmod(0o444)
    try:
        r = client.post(f"/api/sessions/{sid}/restore", json={"ids": [1]}, headers=H)
    finally:
        (repo / "agent/core.py").chmod(0o644)
    body = r.json()
    assert r.status_code == 409 and body["error"].startswith("Undid 0 of 1 file changes")
    assert body["left"] == [{"id": 1, "path": "agent/core.py", "ok": True, "reason": ""}]
    assert not client.get(f"/api/sessions/{sid}").json()["busy"]  # the session isn't left marked busy


def test_restore_and_rewind_report_changes_kept_as_listed(cfg, store, repo):
    client, sid, mid = _auto_applied(cfg, store, repo)
    r = client.post(f"/api/sessions/{sid}/restore", json={"ids": [], "keep": [1]}, headers=H).json()
    assert r["reverted"] == [] and r["left"] == [{"id": 1, "path": "agent/core.py", "ok": False,
                                                  "reason": "left as it was listed"}]
    assert r["message"] == "Undid 0 file changes; left 1 as is: agent/core.py #1 (left as it was listed)."
    events = ndjson(client.post(f"/api/sessions/{sid}/rewind", json={"mid": mid, "message": "again", "restore": [],
                                                                    "keep": [1]}, headers=H))
    assert any(e["type"] == "notice" and "left 1 as is" in e["message"] for e in events)
    assert store.get_proposal(1).status == "applied"
    assert client.post(f"/api/sessions/{sid}/restore", json={"ids": [], "keep": "1"}, headers=H).status_code == 400


def test_verify_endpoint_streams_a_receipt_and_the_session_carries_it(client_and_llm, repo):
    client, _ = client_and_llm
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    ndjson(client.post(f"/api/sessions/{sid}/chat", json={"message": "fix add"}, headers=H))  # leaves #1 pending
    assert client.get(f"/api/sessions/{sid}").json()["receipt"] is None
    events = ndjson(client.post(f"/api/sessions/{sid}/verify", json={}, headers=H))
    assert [e["type"] for e in events] == ["verifying", "verification", "done"]
    assert events[1]["receipt"]["proposal_ids"] == [1] and events[1]["receipt"]["status"] == "pass"
    receipt = client.get(f"/api/sessions/{sid}").json()["receipt"]
    assert receipt["id"] == events[1]["receipt"]["id"] and receipt["proposal_ids"] == [1]
    assert "a - b" in (repo / "agent/core.py").read_text()


def test_verify_waits_while_the_session_is_working(cfg, store, repo):
    gate = threading.Event()

    class GatedLLM(FakeLLM):
        def stream(self, model, system, messages, tools=None, max_tokens=None):
            gate.wait(10)
            yield from super().stream(model, system, messages, tools, max_tokens)

    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=GatedLLM([[{"text": "slow"}]]))))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    with client.stream("POST", f"/api/sessions/{sid}/chat", json={"message": "hi"}, headers=H) as r:
        next(r.iter_lines())
        busy = client.post(f"/api/sessions/{sid}/verify", json={}, headers=H)
        gate.set()
    assert busy.status_code == 409


def test_leftover_verification_copies_are_removed_at_start(cfg, store):
    leftover = cfg.home / "verify" / "abc" / "copy"
    leftover.mkdir(parents=True)
    (leftover / "big.bin").write_bytes(b"x" * 10)
    with TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([])))):
        assert not (cfg.home / "verify").exists()


def test_two_applies_of_one_change_at_once_write_it_once(cfg, store, repo, monkeypatch):
    """A double-click, a held key or two tabs: the second Apply arrives while the first is still running its checks."""
    from codepilot import checks, tools
    root = repo.resolve()
    sess = store.create_session(str(root), "main")
    ctx = tools.ToolContext(root=root, cfg=cfg, store=store, session_id=sess.id)
    # The new text keeps the old, so applying it twice would insert the import twice.
    tools.propose_edit(ctx, "agent/core.py", "def add(a, b):", "import math\n\n\ndef add(a, b):")
    pid = store.list_proposals(sess.id)[-1].id
    entered, release, seen = threading.Event(), threading.Event(), []
    real = checks.quick_check

    def held_first(root_, path):  # the first apply waits here, with its write done and not yet recorded
        seen.append(path)
        if len(seen) == 1:
            entered.set()
            release.wait(5)
        return real(root_, path)

    monkeypatch.setattr(checks, "quick_check", held_first)
    client = TestClient(create_app(replace(cfg, terminal=False), store, Agent(cfg, store, llm=FakeLLM([]))))
    codes = []
    first = threading.Thread(target=lambda: codes.append(client.post(f"/api/proposals/{pid}/apply", headers=H)
                                                         .status_code))
    first.start()
    assert entered.wait(5)
    second = client.post(f"/api/proposals/{pid}/apply", headers=H)
    release.set()
    first.join(5)
    assert (root / "agent" / "core.py").read_text().count("import math") == 1
    assert codes == [200] and second.status_code == 409 and "already" in second.json()["error"]
    assert store.get_proposal(pid).status == "applied"


def test_dismissing_the_plan(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([[tool_use("p1", "update_plan", items=[
        {"text": "Write tests", "status": "done"}, {"text": "Implement it", "status": "doing"}])], [{"text": "paused"}]]))
    client = TestClient(create_app(replace(cfg, terminal=False), store, agent))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    assert client.post(f"/api/sessions/{sid}/plan/dismiss", headers=H).status_code == 409  # no plan yet
    client.post(f"/api/sessions/{sid}/chat", json={"message": "plan it"}, headers=H)
    resp = client.post(f"/api/sessions/{sid}/plan/dismiss", headers=H)
    assert resp.status_code == 200 and resp.json()["dismissed"] and resp.json()["retired"]["progress"] == [1, 2]
    events = client.get(f"/api/sessions/{sid}").json()["events"]
    assert [e for e in events if e["type"] == "plan"][-1]["dismissed"]


def test_applying_to_a_file_that_is_no_longer_utf8_fails_cleanly(cfg, store, repo):
    from codepilot import tools
    root = repo.resolve()
    sess = store.create_session(str(root), "main")
    tools.propose_edit(tools.ToolContext(root=root, cfg=cfg, store=store, session_id=sess.id),
                       "agent/core.py", "a - b", "a + b")
    pid = store.list_proposals(sess.id)[-1].id
    legacy = "# café\ndef add(a, b):\n    return a - b\n".encode("latin-1")  # re-saved by another editor
    (root / "agent/core.py").write_bytes(legacy)
    client = TestClient(create_app(replace(cfg, terminal=False), store, Agent(cfg, store, llm=FakeLLM([]))))
    resp = client.post(f"/api/proposals/{pid}/apply", headers=H)
    assert resp.status_code == 409 and "UTF-8" in resp.json()["error"]
    assert store.get_proposal(pid).status == "failed" and (root / "agent/core.py").read_bytes() == legacy


@pytest.mark.parametrize("setting", ["diff.noprefix", "diff.mnemonicPrefix"])
def test_the_working_tree_diff_has_the_usual_prefixes_whatever_git_is_set_to(cfg, store, repo, setting):
    """The page reads file names from `a/` and `b/`; a user's git settings mustn't change them."""
    import subprocess
    for args in (["add", "-A"], ["commit", "-qm", "start"], ["config", setting, "true"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    (repo / "agent" / "core.py").write_text("def add(a, b):\n    return a + b\n")
    client = TestClient(create_app(replace(cfg, terminal=False), store, Agent(cfg, store, llm=FakeLLM([]))))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    diff = client.get(f"/api/sessions/{sid}/git").json()["diff"]
    assert "diff --git a/agent/core.py b/agent/core.py" in diff and "+++ b/agent/core.py" in diff, diff[:200]


def test_a_session_gets_folders_added_and_reads_files_in_them(client_and_llm, repo, tmp_path):
    """Spec multi-folder 1.1–1.4, 2.4: add a folder, refuse what can't be added, read and list it, make it main."""
    client, _ = client_and_llm
    api = tmp_path / "api"
    (api / "src").mkdir(parents=True)
    (api / "src" / "app.py").write_text("PORT = 8000\n")
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    r = client.patch(f"/api/sessions/{sid}", json={"folders": [str(api)]}, headers=H)
    assert r.status_code == 200 and r.json()["session"]["folders"] == [str(api.resolve())]
    assert client.get(f"/api/sessions/{sid}").json()["session"]["folders"] == [str(api.resolve())]
    for bad, why in [(str(repo / "agent"), "inside"), (str(tmp_path / "nope"), "doesn't exist")]:
        r = client.patch(f"/api/sessions/{sid}", json={"folders": [str(api), bad]}, headers=H)
        assert r.status_code == 400 and why in r.json()["error"]
    listed = client.get(f"/api/sessions/{sid}/files", params={"path": str(api)}).json()["entries"]
    assert listed == [{"name": "src", "path": str((api / "src").resolve()), "dir": True}]
    opened = client.get(f"/api/sessions/{sid}/files", params={"path": str(api / "src" / "app.py")}).json()
    assert opened["content"] == "PORT = 8000\n"
    assert client.get(f"/api/sessions/{sid}/files", params={"path": str(tmp_path)}).status_code == 404  # outside

    r = client.patch(f"/api/sessions/{sid}", json={"make_main": str(api)}, headers=H).json()["session"]
    assert r["repo"] == str(api.resolve()) and r["folders"] == [str(repo.resolve())]
    r = client.patch(f"/api/sessions/{sid}", json={"folders": []}, headers=H).json()["session"]
    assert r["folders"] == []  # removed


def test_files_in_an_added_folder_are_saved_created_and_renamed(client_and_llm, repo, tmp_path):
    """Spec multi-folder 2.4: the editor and Explorer name an added folder's files by full path."""
    client, _ = client_and_llm
    api = tmp_path / "api"
    api.mkdir()
    (api / "app.py").write_text("x = 1\n")
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    client.patch(f"/api/sessions/{sid}", json={"folders": [str(api)]}, headers=H)
    app = str((api / "app.py").resolve())

    def fs(**body):
        return client.post(f"/api/sessions/{sid}/fs", json=body, headers=H)

    assert fs(op="save", path=app, content="x = 2\n").status_code == 200
    assert (api / "app.py").read_text() == "x = 2\n"
    assert fs(op="new_file", path=str(api.resolve() / "new.py")).json()["path"] == str(api.resolve() / "new.py")
    assert fs(op="rename", path=str(api.resolve() / "new.py"), to=str(api.resolve() / "renamed.py")).status_code == 200
    assert (api / "renamed.py").exists()
    (tmp_path / "other.py").write_text("secret\n")
    r = fs(op="save", path=str(tmp_path.resolve() / "other.py"), content="pwned\n")
    assert r.status_code >= 400 and (tmp_path / "other.py").read_text() == "secret\n"  # outside: refused


# -- multi-folder: from review -------------------------------------------------------------------------------------


def _with_api(client, repo, tmp_path):
    api = tmp_path / "api"
    (api / "agent").mkdir(parents=True)
    (api / "agent" / "core.py").write_text("def add(a, b):\n    return a - b\n")  # the same file as the main folder's
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    client.patch(f"/api/sessions/{sid}", json={"folders": [str(api)]}, headers=H)
    return api, sid


def test_making_a_folder_main_keeps_each_change_on_its_own_file(client_and_llm, store, repo, tmp_path):
    client, _ = client_and_llm
    api, sid = _with_api(client, repo, tmp_path)
    ndjson(client.post(f"/api/sessions/{sid}/chat", json={"message": "fix add"}, headers=H))  # agent/core.py, main
    [prop] = store.list_proposals(sid)
    client.patch(f"/api/sessions/{sid}", json={"make_main": str(api)}, headers=H)
    assert store.get_proposal(prop.id).path == str((repo / "agent" / "core.py").resolve())  # still the old main's
    assert client.post(f"/api/proposals/{prop.id}/apply", headers=H).status_code == 200
    assert "a + b" in (repo / "agent" / "core.py").read_text()
    assert "a - b" in (api / "agent" / "core.py").read_text()  # not the new main folder's file of the same name
    client.patch(f"/api/sessions/{sid}", json={"make_main": str(repo)}, headers=H)
    assert store.get_proposal(prop.id).path == "agent/core.py"  # back in the main folder: relative again


def test_folders_cant_change_while_the_session_is_working(cfg, store, repo, tmp_path):
    gate = threading.Event()

    class GatedLLM(FakeLLM):
        def stream(self, model, system, messages, tools=None, max_tokens=None):
            gate.wait(10)
            yield from super().stream(model, system, messages, tools, max_tokens)

    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=GatedLLM([[{"text": "ok"}]]))))
    api, sid = _with_api(client, repo, tmp_path)
    with client.stream("POST", f"/api/sessions/{sid}/chat", json={"message": "hi"}, headers=H) as r:
        next(r.iter_lines())
        removing = client.patch(f"/api/sessions/{sid}", json={"folders": []}, headers=H)
        making = client.patch(f"/api/sessions/{sid}", json={"make_main": str(api)}, headers=H)
        gate.set()
    assert removing.status_code == 409 and making.status_code == 409 and "working" in removing.json()["error"]
    assert store.get_session(sid).folders == [str(api.resolve())]


def test_a_link_back_up_an_added_folder_lists_under_the_path_asked_for(client_and_llm, repo, tmp_path):
    client, _ = client_and_llm
    api, sid = _with_api(client, repo, tmp_path)
    (api / "loop").symlink_to(api)
    loop = str(api.resolve() / "loop")
    listed = client.get(f"/api/sessions/{sid}/files", params={"path": loop}).json()["entries"]
    assert {e["path"] for e in listed} >= {f"{loop}/agent", f"{loop}/loop"}  # deeper each time: no endless tree


def test_search_go_to_file_and_git_reach_an_added_folder(client_and_llm, repo, tmp_path):
    """Spec multi-folder 3.1, 3.3: the Search view, ⌘P and the Changes view."""
    import subprocess

    client, _ = client_and_llm
    api, sid = _with_api(client, repo, tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "trunk", str(api)], check=True)
    (api / "README.md").write_text("PORT notes\n")
    core = str((api / "agent" / "core.py").resolve())
    hits = client.get(f"/api/sessions/{sid}/grep", params={"q": "return a - b"}).json()["results"]
    assert {h["path"] for h in hits} == {"agent/core.py", core}
    assert core in client.get(f"/api/sessions/{sid}/find", params={"q": "core.py"}).json()["files"]
    g = client.get(f"/api/sessions/{sid}/git").json()
    [other] = g["folders"]
    assert other["path"] == str(api.resolve()) and other["git"] and other["branch"] == "trunk"
    assert "README.md" in {f["path"] for f in other["files"]}


def test_an_added_folders_changes_are_listed_by_their_real_names(client_and_llm, repo, tmp_path):
    import subprocess

    client, _ = client_and_llm
    api, sid = _with_api(client, repo, tmp_path)
    git = ["git", "-C", str(api), "-c", "user.name=T", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(api)], check=True)
    (api / "old.py").write_text("x = 1\n")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    subprocess.run([*git, "mv", "old.py", "new.py"], check=True)
    (api / "my file é.py").write_text("y = 2\n")
    [other] = client.get(f"/api/sessions/{sid}/git").json()["folders"]
    assert {(f["path"], f["code"]) for f in other["files"]} >= {("new.py", "R"), ("my file é.py", "??")}


def test_a_refused_make_main_leaves_the_changes_alone(client_and_llm, store, repo, tmp_path):
    client, _ = client_and_llm
    api, sid = _with_api(client, repo, tmp_path)
    ndjson(client.post(f"/api/sessions/{sid}/chat", json={"message": "fix add"}, headers=H))
    [prop] = store.list_proposals(sid)
    import shutil
    shutil.rmtree(api)
    r = client.patch(f"/api/sessions/{sid}", json={"make_main": str(api)}, headers=H)
    assert r.status_code == 400
    assert store.get_proposal(prop.id).path == "agent/core.py" and store.get_session(sid).repo == str(repo.resolve())
