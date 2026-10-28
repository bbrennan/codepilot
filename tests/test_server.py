import json
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
