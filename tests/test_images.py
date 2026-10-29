"""Images: pasted, linked, local paths, @-references, view_image, providers, context estimates, endpoints."""

import base64
import json
import os
import struct
import sys
import zlib

import pytest
from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot import images
from codepilot.agent import Agent, history_events
from codepilot.anthropic_api import to_anthropic
from codepilot.context import _chars
from codepilot.ollama import to_ollama_messages
from codepilot.openai_api import to_openai
from codepilot.server import create_app
from codepilot.tools import build_tools

H = {"X-Codepilot": "1"}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9a"
                       "wAAAABJRU5ErkJggg==")
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 20
GIF = b"GIF89a" + b"\0" * 20
WEBP = b"RIFF\0\0\0\0WEBPVP8 " + b"\0" * 10


def smoke_png(w, h, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


def test_sniff_and_limits():
    assert [images.sniff(x) for x in (PNG, JPEG, GIF, WEBP, b"hello")] == ["png", "jpeg", "gif", "webp", None]
    with pytest.raises(images.ImageError):
        images.block(b"<svg/>")
    with pytest.raises(images.ImageError):
        images.block(PNG + b"\0" * images.MAX_BYTES)
    assert images.block(PNG)["image"]["format"] == "png"


def test_images_the_user_points_at(repo, tmp_path, monkeypatch):
    shot = tmp_path / "Desktop" / "shot.png"
    shot.parent.mkdir()
    shot.write_bytes(PNG)
    (repo / "docs").mkdir()
    (repo / "docs" / "arch.png").write_bytes(PNG)
    fetched = []
    monkeypatch.setattr(images, "fetch", lambda url: fetched.append(url) or PNG)
    text = (f"compare {shot} with @docs/arch.png and https://example.com/a/ui.png?v=2 "
            "but not https://example.com/page or /no/such/file.png")
    found, problems = images.from_message(text, repo)
    assert [src for _, src in found] == ["https://example.com/a/ui.png?v=2", str(shot), "@docs/arch.png"]
    assert fetched == ["https://example.com/a/ui.png?v=2"] and problems == []


def test_a_bad_link_is_reported_not_fatal(repo, monkeypatch):
    def boom(url):
        raise images.ImageError("couldn't download it: 404")
    monkeypatch.setattr(images, "fetch", boom)
    found, problems = images.from_message("see https://example.com/x.png", repo)
    assert found == [] and "404" in problems[0]


def test_pasted_image_reaches_the_model_and_the_ui(cfg, store, repo):
    llm = FakeLLM([[{"text": "I see a dot"}]])
    agent = Agent(cfg, store, llm=llm)
    client = TestClient(create_app(cfg, store, agent))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    body = {"message": "", "images": [{"data": base64.b64encode(PNG).decode(), "media_type": "image/png"}]}
    events = [json.loads(x) for x in client.post(f"/api/sessions/{sid}/chat", json=body, headers=H).text.splitlines()]
    shown = next(e for e in events if e["type"] == "attached_images")["images"][0]
    assert shown["source"] == "pasted" and client.get(shown["url"]).content == PNG
    sent = llm.calls[-1]["messages"][-1]["content"]
    assert sent[0]["text"] == "(see the attached image)" and any("image" in b for b in sent)
    replay = history_events(store, sid)
    assert any(e["type"] == "attached_images" for e in replay)
    bad = {"message": "x", "images": [{"data": base64.b64encode(b"not an image").decode()}]}
    assert client.post(f"/api/sessions/{sid}/chat", json=bad, headers=H).status_code == 400
    assert client.get("/api/images/../../etc/passwd").status_code == 404


def test_view_image_tool(cfg, store, repo):
    (repo / "shot.png").write_bytes(PNG)
    llm = FakeLLM([[tool_use("t1", "view_image", source="shot.png")], [{"text": "looks fine"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "check the screenshot"))
    result = next(e for e in events if e["type"] == "tool_result")
    assert not result["is_error"] and result["images"][0].startswith("/api/images/")
    tr = next(b["toolResult"] for b in llm.calls[-1]["messages"][-1]["content"] if "toolResult" in b)
    assert any("image" in c for c in tr["content"])
    assert any("images" in e for e in history_events(store, sess.id) if e["type"] == "tool_result")


def test_providers_translate_images():
    img = images.block(PNG)
    msgs = [
        {"role": "user", "content": [{"text": "look"}, img]},
        {"role": "assistant", "content": [tool_use("t1", "view_image", source="a.png")]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "status": "success",
                                                     "content": [{"text": "attached"}, img]}}]},
    ]
    a = to_anthropic(msgs)
    assert a[0]["content"][1]["type"] == "image" and a[0]["content"][1]["source"]["media_type"] == "image/png"
    assert a[2]["content"][0]["content"][1]["type"] == "image"
    o = to_openai(msgs)
    assert o[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert o[2]["role"] == "tool" and o[3]["role"] == "user" and o[3]["content"][1]["type"] == "image_url"
    ol = to_ollama_messages(msgs)
    assert ol[0]["images"] and ol[-1]["role"] == "user" and ol[-1]["images"]


def test_images_cost_tokens_not_bytes():
    big = {"image": {"format": "png", "source": {"bytes": b"\0" * 3_000_000}}}
    assert 4000 < _chars([big]) < 6000


def test_old_images_are_pruned_first(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([]))
    sess = store.create_session(str(repo), "main")
    store.add_message(sess.id, "user", [{"text": "old"}, images.block(PNG)])
    store.add_message(sess.id, "assistant", [{"text": "ok " * 10}])
    cleared, freed = agent.ctxm.prune(sess.id, protect_tokens=10, min_free_tokens=1)
    assert cleared == 1 and freed > 0
    assert store.live_messages(sess.id)[0]["content"][1] == {"text": "[image removed to free context]"}


def test_macos_screenshot_paths_with_spaces_are_found(repo, tmp_path):
    desk = tmp_path / "Desktop"
    desk.mkdir()
    # macOS names screenshots with a narrow no-break space before AM/PM, which nobody types.
    shot = desk / "Screenshot 2026-10-25 at 3.14.15 PM.png"
    shot.write_bytes(PNG)
    other = desk / "Screen Shot 2.png"
    other.write_bytes(PNG)
    typed = f"why does this fail? {desk}/Screenshot 2026-10-25 at 3.14.15 PM.png thanks"
    found, problems = images.from_message(typed, repo)
    assert [src for _, src in found] == [str(shot)] and problems == []
    for text in (f'look at "{other}"', f"look at {str(other).replace(' ', chr(92) + ' ')}",
                 f"both are in {desk}: {other}"):
        assert [src for _, src in images.from_message(text, repo)[0]] == [str(other)], text


def test_workspace_images_with_and_without_at(repo):
    (repo / "shots").mkdir()
    (repo / "shots" / "login page.png").write_bytes(PNG)
    (repo / "shots" / "home.png").write_bytes(PNG)
    found, _ = images.from_message('see @"shots/login page.png" and shots/home.png', repo)
    assert [src for _, src in found] == ["@shots/login page.png", "@shots/home.png"]


@pytest.mark.skipif(sys.platform != "darwin", reason="uses macOS's sips to shrink images")
def test_oversized_screenshots_are_shrunk(tmp_path):
    w = h = 1300
    raw = b"".join(b"\x00" + os.urandom(w * 3) for _ in range(h))  # noise: doesn't compress
    big = tmp_path / "retina.png"
    big.write_bytes(smoke_png(w, h, raw))
    assert big.stat().st_size > images.MAX_BYTES
    data = images.load_path(big)
    assert len(data) <= images.MAX_BYTES and images.sniff(data) in ("png", "jpeg")


def test_view_image_outside_the_workspace_asks_first(cfg, store, repo, tmp_path):
    desk = tmp_path / "Desktop"
    desk.mkdir()
    (desk / "Screenshot 1.04.05 PM.png").write_bytes(PNG)
    (repo / "in.png").write_bytes(PNG)
    tool = {t.name: t for t in build_tools(cfg)}["view_image"]
    assert not tool.requires_approval({"source": "in.png"}, False, repo)
    assert not tool.requires_approval({"source": "https://x.io/a.png"}, False, repo)
    assert tool.requires_approval({"source": f"{desk}/x.png"}, False, repo)
    llm = FakeLLM([[tool_use("t1", "view_image", source=f"{desk}/Screenshot 1.04.05 PM.png")], [{"text": "a form"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = store.create_session(str(repo), "main")
    events = list(agent.chat(sess.id, "what's in my screenshot?"))
    assert events[-1]["type"] == "approval_needed" and events[-1]["tools"][0]["command"].startswith("view image ")
    result = next(e for e in list(agent.resume(sess.id, approve=True)) if e["type"] == "tool_result")
    assert not result["is_error"] and result["images"]
    missing = list(Agent(cfg, store, llm=FakeLLM([[tool_use("t2", "view_image", source="nope.png")],
                                                    [{"text": "ok"}]])).chat(sess.id, "again"))
    err = next(e for e in missing if e["type"] == "tool_result")
    assert err["is_error"] and "Images in that folder: in.png" in err["output"]


def test_the_model_is_told_it_can_see_images():
    from codepilot.prompts import STATIC
    assert "You can see images" in STATIC and "view_image" in STATIC


def test_image_links_never_reach_cloud_metadata_or_follow_cross_site_redirects(monkeypatch):
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("169.254.169.254", 80))])
    with pytest.raises(images.ImageError, match="link-local"):
        images.fetch("http://169.254.169.254/latest/meta-data/")

    opened = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 80))])

    class Opener:
        def open(self, req, timeout=None):
            opened.append(req.full_url)
            raise OSError("offline")

    import urllib.request
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: (opened.append([type(h).__name__ if not isinstance(h, type) else h.__name__ for h in handlers]), Opener())[1])
    with pytest.raises(images.ImageError, match="couldn't download"):
        images.fetch("https://example.com/a.png")
    assert any("SameHost" in str(h) for h in opened[0])  # redirects are limited to the same host
