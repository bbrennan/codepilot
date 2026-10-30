"""Hostile and malformed input at every HTTP route must produce a clean 4xx/2xx, never a 500 or a hang."""

import itertools

import pytest
from fakes import FakeLLM
from starlette.routing import Route
from starlette.testclient import TestClient

from codepilot.agent import Agent
from codepilot.server import create_app

H = {"X-Codepilot": "1"}
SKIP = {"/api/restart", "/api/report",  # restart execs the process; report posts to GitHub
        "/api/terminals", "/api/terminals/{tid}"}  # need the page's terminal token; see tests/test_terminal.py
WEIRD = ["", "..", "../../etc/passwd", "/etc/passwd", "~", "a\x00b", "é☃😀", "a" * 5000, "-1", "x/../../y", "\n", ".git/config"]
BODIES = [None, {}, [], "str", 5, {"path": 5}, {"path": None}, {"op": []}, {"text": {"a": 1}}, {"id": {}},
          {"path": "../../x", "to": "/etc/x", "op": "rename"}, {"images": "x"}, {"message": 5}]


@pytest.fixture
def api(cfg, store, repo, monkeypatch):
    from codepilot import github, models

    # The sweep must never reach the network: model discovery sends (billable) probes, GitHub status runs `gh`.
    monkeypatch.setattr(models, "discover", lambda *a, **k: {"models": [], "tiers": {}, "provider": "bedrock"})
    monkeypatch.setattr(github, "status", lambda *a, **k: {"available": False, "reason": "stubbed"})
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))), raise_server_exceptions=False)
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    return client, sid


def routes(app):
    for r in app.routes:
        if isinstance(r, Route) and r.path not in SKIP:
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield r.path, m


def test_no_route_answers_500_to_hostile_input(api, repo):
    client, sid = api
    bad = []
    for path, method in routes(client.app):
        concrete = path.replace("{sid}", sid)
        for name in ("{tid}", "{qid}", "{pid:int}", "{name}", "{action}", "{action:str}"):
            concrete = concrete.replace(name, "1")
        if "{" in concrete or (method == "DELETE" and concrete.endswith(sid)):
            continue
        if method == "GET":
            attempts = [dict(params={k: w}) for k, w in itertools.product(["path", "q", "limit"], WEIRD)]
        else:
            attempts = [dict(json=b) for b in BODIES] + [dict(content=b"{not json", headers={"content-type": "application/json"})]
        for kw in attempts:
            kw["headers"] = {**H, **kw.get("headers", {})}
            r = client.request(method, concrete, **kw)
            if r.status_code >= 500:
                bad.append((method, concrete, {k: (str(v)[:60]) for k, v in kw.items() if k != "headers"}, r.status_code,
                            r.text[:100]))
    assert not bad, f"{len(bad)} server errors, e.g.\n" + "\n".join(sorted({f"{b[0]} {b[1][:30]}.. {b[2]}" for b in bad}))


def test_bad_input_is_a_400_with_a_message(api):
    client, sid = api
    for url, kw in [(f"/api/sessions/{sid}/fs", dict(content=b"{not json", headers={"content-type": "application/json"})),
                    (f"/api/sessions/{sid}/chat", dict(json=[1, 2])), (f"/api/sessions/{sid}/chat", dict(json={"message": 5}))]:
        r = client.post(url, **{**kw, "headers": {**H, **kw.get("headers", {})}})
        assert r.status_code == 400 and r.json()["error"], (url, r.text)
    assert client.get(f"/api/sessions/{sid}/files", params={"path": "a\x00b"}).status_code == 400
    assert client.get(f"/api/sessions/{sid}/files", params={"path": "a" * 5000}).status_code == 400
    assert client.post(f"/api/sessions/{sid}/chat", headers=H, content=b"").status_code == 400  # no body at all


def test_routes_that_parse_the_body_first_reject_bad_json_with_400(api):
    """The sweep above only proves "not 500". These routes read the body before anything else, so a bad body must
    be a 400 specifically: reverting json_body/HANDLERS turns each into a 500."""
    client, sid = api
    for path in ("approve", "queue", "rewind", "compact", "run", "fs", "chat"):
        for body in (b"{not json", b"[1]", b'"str"'):
            r = client.post(f"/api/sessions/{sid}/{path}", content=body,
                            headers={**H, "content-type": "application/json"})
            assert r.status_code == 400, (path, body, r.status_code, r.text[:80])


def test_a_deeply_nested_body_is_a_400_not_a_recursion_crash(api):
    client, sid = api
    r = client.post(f"/api/sessions/{sid}/fs", content=b"[" * 200_000, headers={**H, "content-type": "application/json"})
    assert r.status_code == 400


def test_only_caller_mistakes_are_translated_a_missing_program_is_still_a_server_error():
    import asyncio
    import errno
    from types import SimpleNamespace

    from codepilot import http_input

    req = SimpleNamespace(url=SimpleNamespace(path="/api/sessions/x/git"))
    run = lambda e: asyncio.run(http_input._os_error(req, e)).status_code  # noqa: E731
    assert run(OSError(errno.ENAMETOOLONG, "File name too long")) == 400
    assert run(OSError(errno.ENOENT, "No such file or directory: 'git'")) == 500  # e.g. git not installed
    assert run(OSError(errno.EACCES, "Permission denied")) == 500
