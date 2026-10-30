"""Built-in web tools: page fetching and its safety rules, Context7 docs, Brave search, approvals."""

import base64
import http.server
import json
import threading
from dataclasses import replace

import pytest
from fakes import FakeLLM, tool_use

from codepilot import webtools
from codepilot.agent import Agent, allow_rule, rule_matches
from codepilot.tools import build_tools

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9a"
                       "wAAAABJRU5ErkJggg==")
PAGE = b"""<!doctype html><html><head><title>Runtime guide</title><script>evil()</script></head><body>
<nav>menu</nav><h1>Invoke an agent</h1><p>Call <a href="https://example.com/api">the API</a> with a session id.</p>
<ul><li>first</li><li>second</li></ul><pre>client.invoke(
    payload)</pre></body></html>"""


@pytest.fixture
def site():
    routes = {
        "/page": (200, "text/html; charset=utf-8", PAGE),
        "/shot": (200, "image/png", PNG),
        "/doc.pdf": (200, "application/pdf", b"%PDF-1.7 ..."),
        "/elsewhere": (302, "text/plain", b""),
        "/same": (302, "text/plain", b""),
        "/missing": (404, "text/plain", b"nope"),
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            code, ctype, body = routes.get(self.path, (404, "text/plain", b""))
            self.send_response(code)
            if self.path == "/elsewhere":
                self.send_header("Location", f"http://localhost:{self.server.server_address[1]}/page")
            if self.path == "/same":
                self.send_header("Location", "/page")
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_html_to_text():
    title, text = webtools.html_to_text(PAGE.decode())
    assert title == "Runtime guide" and "evil" not in text
    assert "# Invoke an agent" in text and "the API (https://example.com/api)" in text
    assert "- first" in text and "client.invoke(\n    payload)" in text


def test_fetch_page_text_image_and_refusals(site):
    page = webtools.fetch_page(site + "/page")
    assert page["kind"] == "text" and page["title"] == "Runtime guide"
    assert webtools.fetch_page(site + "/shot")["kind"] == "image"
    assert webtools.fetch_page(site + "/same")["title"] == "Runtime guide"  # same-site redirect is fine
    with pytest.raises(webtools.WebError, match="redirects to another site"):
        webtools.fetch_page(site + "/elsewhere")  # 127.0.0.1 -> localhost
    with pytest.raises(webtools.WebError, match="PDF"):
        webtools.fetch_page(site + "/doc.pdf")
    with pytest.raises(webtools.WebError, match="HTTP 404"):
        webtools.fetch_page(site + "/missing")


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data/", "ftp://example.com/x", "file:///etc/passwd"])
def test_never_fetched(url):
    with pytest.raises(webtools.WebError):
        webtools.fetch_page(url)


def test_library_docs_uses_the_best_match(monkeypatch):
    calls = []

    def fake(path, params, key, raw=False):
        calls.append((path, params, key))
        if path == "libs/search":
            return {"results": [{"id": "/aws/bedrock-agentcore-sdk-python", "title": "Bedrock AgentCore SDK"},
                                {"id": "/awslabs/agentcore-samples", "title": "Samples"}]}
        return "### Invoke\nruntime.invoke(...)"
    monkeypatch.setattr(webtools, "_context7", fake)
    out = webtools.library_docs("bedrock agentcore", "invoke with streaming", key="k")
    assert "runtime.invoke" in out and "Samples (/awslabs/agentcore-samples)" in out
    assert calls[1][1]["libraryId"] == "/aws/bedrock-agentcore-sdk-python" and calls[0][2] == "k"


def test_web_search(monkeypatch):
    body = {"web": {"results": [{"title": "AgentCore", "url": "https://aws.amazon.com/x",
                                 "description": "Run <strong>agents</strong>"}]}}
    monkeypatch.setattr(webtools, "_get", lambda url, headers=None: (json.dumps(body).encode(), "", url))
    assert "1. AgentCore\n   https://aws.amazon.com/x\n   Run agents" in webtools.web_search("agentcore", "key")


def test_fetch_rules_are_per_exact_host():
    tu = {"name": "web_fetch", "input": {"url": "https://docs.aws.amazon.com/bedrock/latest/x.html"}}
    rule = allow_rule(tu)
    assert rule == {"tool": "web_fetch", "prefix": "docs.aws.amazon.com"}
    assert rule_matches(rule, {"name": "web_fetch", "input": {"url": "https://docs.aws.amazon.com/other"}})
    assert not rule_matches(rule, {"name": "web_fetch", "input": {"url": "https://evil.docs.aws.amazon.com.x.io/"}})
    assert not rule_matches(rule, {"name": "web_fetch", "input": {"url": "https://aws.amazon.com/"}})


def test_which_web_tools_are_offered(cfg):
    names = {t.name for t in build_tools(cfg)}
    assert {"library_docs", "web_fetch"} <= names and "web_search" not in names
    assert "web_search" in {t.name for t in build_tools(replace(cfg, brave_api_key="k"))}
    assert not {"library_docs", "web_fetch"} & {t.name for t in build_tools(replace(cfg, web_tools=False))}


def test_web_fetch_asks_first(cfg, store, repo, site):
    llm = FakeLLM([[tool_use("t1", "web_fetch", url=site + "/page")], [{"text": "read it"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "read the guide"))
    assert events[-1]["type"] == "approval_needed" and events[-1]["tools"][0]["command"] == f"fetch {site}/page"
    events = list(agent.resume(sess.id, approve=True))
    result = next(e for e in events if e["type"] == "tool_result")
    assert "# Runtime guide" in result["output"] and "Invoke an agent" in result["output"]


def test_ipv4_mapped_ipv6_metadata_addresses_are_refused(monkeypatch):
    import pytest

    from codepilot import webtools

    for url in ["http://[::ffff:169.254.169.254]/latest/meta-data/", "http://[::ffff:a9fe:a9fe]/", "http://[fd00:ec2::254]/"]:
        with pytest.raises(webtools.WebError, match="link-local"):
            webtools.check_target(url)


def test_dns_rebinding_cannot_reach_metadata_between_the_check_and_the_connection(monkeypatch):
    """The name is looked up again when connecting. A hostile DNS server can answer a public address for the
    pre-check and the metadata address for the connection, so the address actually connected to is vetted."""
    import socket

    import pytest

    from codepilot import webtools

    answers = iter(["93.184.216.34", "169.254.169.254", "169.254.169.254"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [(2, 1, 6, "", (next(answers), port or 80))])
    connected = []
    monkeypatch.setattr(socket, "create_connection", lambda addr, *a, **k: connected.append(addr) or (_ for _ in ()).throw(OSError("no network in tests")))
    with pytest.raises(webtools.WebError, match="link-local"):
        webtools._get("http://rebind.example/latest/meta-data/")
    assert not [c for c in connected if c[0].startswith("169.254")], connected


def test_normal_http_fetching_still_works_through_the_guard():
    import http.server
    import threading

    from codepilot import webtools

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"hello through the guard")

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        data, ctype, _ = webtools._get(f"http://127.0.0.1:{server.server_port}/x")
        assert data == b"hello through the guard" and ctype.startswith("text/plain")
    finally:
        server.shutdown()
