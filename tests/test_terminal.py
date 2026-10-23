"""Server-side terminals: lifecycle, scrollback, reattach, limits, and the locked-down endpoints."""

import json
import re
import time
from dataclasses import replace

import pytest
from fakes import FakeLLM
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from codepilot.agent import Agent
from codepilot.server import create_app
from codepilot.terminal import EXITED, UNKNOWN, TerminalLimit, TerminalManager

H = {"X-Codepilot": "1"}
ORIGIN = {"origin": "http://testserver"}


def wait_for(fn, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out waiting")


@pytest.fixture
def manager():
    m = TerminalManager(shell="/bin/sh")
    yield m
    m.close_all()


def test_runs_in_folder_and_keeps_scrollback(manager, tmp_path):
    term = manager.create(tmp_path, "build")
    term.write("pwd; echo marker-$((6*7))\n")
    wait_for(lambda: "marker-42" in term.scrollback())
    assert tmp_path.name in term.scrollback()
    info = term.info()
    assert info["name"] == "build" and info["alive"] and info["shell"] == "sh" and info["cwd"] == str(tmp_path)

    late = []
    history = term.subscribe(late.append)  # a client attaching later gets everything so far, then live output
    assert "marker-42" in history
    term.write("echo after-attach\n")
    wait_for(lambda: "after-attach" in "".join(c for c in late if c))


def test_exit_code_is_reported_to_subscribers(manager, tmp_path):
    term = manager.create(tmp_path)
    seen = []
    term.subscribe(seen.append)
    term.write("exit 3\n")
    wait_for(lambda: None in seen)
    assert not term.alive and term.exit_code == 3
    assert manager.get(term.id) is term  # stays listed so the user can read why it failed


def test_kill_stops_the_shell(manager, tmp_path):
    term = manager.create(tmp_path)
    assert manager.kill(term.id)
    assert manager.get(term.id) is None and term.pty.proc.poll() is not None
    assert not manager.kill(term.id)


def test_limit_counts_only_running_terminals(tmp_path):
    m = TerminalManager(max_terminals=2, shell="/bin/sh")
    try:
        a = m.create(tmp_path)
        m.create(tmp_path)
        with pytest.raises(TerminalLimit):
            m.create(tmp_path)
        a.write("exit\n")
        wait_for(lambda: not a.alive)
        m.create(tmp_path)  # an exited terminal no longer counts
    finally:
        m.close_all()


def test_scrollback_is_capped_at_a_line_boundary(tmp_path):
    m = TerminalManager(scrollback=2000, shell="/bin/sh")
    try:
        term = m.create(tmp_path)
        term.write("i=0; while [ $i -lt 300 ]; do echo line-$i-padding-padding; i=$((i+1)); done; echo done-$((1+1))\n")
        wait_for(lambda: "done-2" in term.scrollback())
        text = term.scrollback()
        assert len(text) <= 2000 and "line-0-" not in text and "line-299-" in text
        assert text.startswith("line-") or text.startswith("\r\n") or text[0].isalnum()
    finally:
        m.close_all()


# -- HTTP and WebSocket endpoints -------------------------------------------------------------------


@pytest.fixture
def app_client(cfg, store):
    app = create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([])))
    app.state.terminals.shell = "/bin/sh"
    with TestClient(app) as client:
        token = re.search(r'name="codepilot-token" content="([^"]*)"', client.get("/").text).group(1)
        yield client, {**H, "X-Codepilot-Terminal": token}, token


def read_until(ws, needle, limit=400):
    seen = ""
    for _ in range(limit):
        seen += ws.receive_text()
        if needle in seen:
            return seen
    raise AssertionError(f"{needle!r} not in {seen[-500:]!r}")


def test_rest_lifecycle(app_client, repo, tmp_path):
    client, th, _ = app_client
    sess = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()
    t1 = client.post("/api/terminals", json={"sid": sess["id"]}, headers=th)
    assert t1.status_code == 201 and t1.json()["cwd"] == str(repo)
    t2 = client.post("/api/terminals", json={"cwd": str(tmp_path), "name": "logs"}, headers=th).json()
    assert t2["cwd"] == str(tmp_path.resolve()) and t2["name"] == "logs"
    listed = client.get("/api/terminals", headers=th).json()["terminals"]
    assert [t["id"] for t in listed] == [t1.json()["id"], t2["id"]]  # oldest first: stable numbering
    assert client.patch(f"/api/terminals/{t2['id']}", json={"name": "server"}, headers=th).json()["name"] == "server"
    assert client.delete(f"/api/terminals/{t2['id']}", headers=th).json()["ok"]
    assert client.get(f"/api/terminals/{t2['id']}", headers=th).status_code == 404
    assert client.post("/api/terminals", json={"cwd": str(tmp_path / "nope")}, headers=th).status_code == 400


def test_rest_requires_token_and_same_origin(app_client):
    client, th, _ = app_client
    assert client.get("/api/terminals", headers=H).status_code == 403
    assert client.post("/api/terminals", json={}, headers={**H, "X-Codepilot-Terminal": "wrong"}).status_code == 403
    evil = {**th, "origin": "http://evil.example"}
    assert client.post("/api/terminals", json={}, headers=evil).status_code == 403
    assert client.post("/api/terminals", json={}, headers={"X-Codepilot-Terminal": th["X-Codepilot-Terminal"]}) \
        .status_code == 403  # CSRF header still required
    assert client.get("/api/terminals", headers=th).json()["terminals"] == []


def test_shell_survives_disconnect_and_replays_on_reattach(app_client, tmp_path):
    """The page reloading must not lose the shell, its state, or what it printed."""
    client, th, token = app_client
    tid = client.post("/api/terminals", json={"cwd": str(tmp_path)}, headers=th).json()["id"]
    url = f"/api/terminal?token={token}&id={tid}"
    with client.websocket_connect(url, headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "resize", "cols": 90, "rows": 20}))
        ws.send_text(json.dumps({"type": "input", "data": "export CP_STATE=kept; echo first-$((20+1))\n"}))
        read_until(ws, "first-21")
    assert client.get(f"/api/terminals/{tid}", headers=th).json()["alive"]
    with client.websocket_connect(url, headers=ORIGIN) as ws:
        assert "first-21" in read_until(ws, "first-21")  # scrollback replayed
        ws.send_text(json.dumps({"type": "input", "data": "echo state-$CP_STATE\n"}))
        read_until(ws, "state-kept")  # same shell process


def test_two_clients_see_the_same_terminal(app_client, tmp_path):
    client, th, token = app_client
    tid = client.post("/api/terminals", json={"cwd": str(tmp_path)}, headers=th).json()["id"]
    url = f"/api/terminal?token={token}&id={tid}"
    with client.websocket_connect(url, headers=ORIGIN) as a, client.websocket_connect(url, headers=ORIGIN) as b:
        a.send_text(json.dumps({"type": "input", "data": "echo shared-$((2*21))\n"}))
        read_until(a, "shared-42")
        read_until(b, "shared-42")


def test_exit_closes_socket_with_exit_code(app_client, tmp_path):
    client, th, token = app_client
    tid = client.post("/api/terminals", json={"cwd": str(tmp_path)}, headers=th).json()["id"]
    with client.websocket_connect(f"/api/terminal?token={token}&id={tid}", headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "input", "data": "exit 7\n"}))
        with pytest.raises(WebSocketDisconnect) as closed:
            read_until(ws, "never-printed")
    assert closed.value.code == EXITED and closed.value.reason == "7"
    info = client.get(f"/api/terminals/{tid}", headers=th).json()
    assert not info["alive"] and info["exit_code"] == 7
    with client.websocket_connect(f"/api/terminal?token={token}&id={tid}", headers=ORIGIN) as ws:
        with pytest.raises(WebSocketDisconnect) as again:  # reattaching to an exited terminal: history, then close
            read_until(ws, "never-printed")
    assert again.value.code == EXITED


def test_unknown_terminal_and_bad_token(app_client):
    client, _, token = app_client
    with client.websocket_connect(f"/api/terminal?token={token}&id=nope", headers=ORIGIN) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert closed.value.code == UNKNOWN
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/terminal?token=bad&id=nope", headers=ORIGIN) as ws:
            ws.receive_text()


def test_limit_returns_429(cfg, store, tmp_path):
    app = create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([])))
    app.state.terminals.max_terminals = 1
    app.state.terminals.shell = "/bin/sh"
    with TestClient(app) as client:
        token = re.search(r'name="codepilot-token" content="([^"]*)"', client.get("/").text).group(1)
        th = {**H, "X-Codepilot-Terminal": token}
        assert client.post("/api/terminals", json={"cwd": str(tmp_path)}, headers=th).status_code == 201
        r = client.post("/api/terminals", json={"cwd": str(tmp_path)}, headers=th)
        assert r.status_code == 429 and "At most 1" in r.json()["error"]


def test_server_shutdown_kills_shells(cfg, store, tmp_path):
    app = create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([])))
    app.state.terminals.shell = "/bin/sh"
    with TestClient(app) as client:
        token = re.search(r'name="codepilot-token" content="([^"]*)"', client.get("/").text).group(1)
        client.post("/api/terminals", json={"cwd": str(tmp_path)}, headers={**H, "X-Codepilot-Terminal": token})
        procs = [t.pty.proc for t in app.state.terminals.list()]
    assert procs and all(p.poll() is not None for p in procs)


def test_disabled_terminal_refuses_rest(cfg, store):
    app = create_app(replace(cfg, terminal=False), store, Agent(cfg, store, llm=FakeLLM([])))
    with TestClient(app) as client:
        assert client.post("/api/terminals", json={}, headers={**H, "X-Codepilot-Terminal": ""}).status_code == 403
