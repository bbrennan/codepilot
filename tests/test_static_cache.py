"""Scripts under /static/ revalidate on every load, so an upgrade never pairs a new app.js with an old cached helper."""
from fakes import FakeLLM
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from codepilot.agent import Agent
from codepilot.server import create_app
from codepilot.static_files import RevalidatedStaticFiles


def _client(directory):
    return TestClient(Starlette(routes=[Mount("/static", app=RevalidatedStaticFiles(directory=directory))]))


def test_every_static_response_says_no_cache(tmp_path):
    (tmp_path / "helper.js").write_text("function stepWaiting() {}\n")
    first = _client(tmp_path).get("/static/helper.js")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-cache"
    assert first.headers["etag"]


def test_unchanged_file_answers_304_with_the_header(tmp_path):
    (tmp_path / "helper.js").write_text("function stepWaiting() {}\n")
    client = _client(tmp_path)
    etag = client.get("/static/helper.js").headers["etag"]
    again = client.get("/static/helper.js", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.headers["cache-control"] == "no-cache"
    assert again.content == b""


def test_the_app_serves_its_scripts_this_way(cfg, store):
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    first = client.get("/static/app.js")
    assert first.headers["cache-control"] == "no-cache"
    assert client.get("/static/app.js", headers={"If-None-Match": first.headers["etag"]}).status_code == 304
