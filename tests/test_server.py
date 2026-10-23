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
    assert client.post(f"/api/sessions/{sess['id']}/cancel", headers=H).json() == {"ok": True}
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
