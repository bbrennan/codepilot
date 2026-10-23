"""Images: pasted, linked, local paths, @-references, view_image, providers, context estimates, endpoints."""

import base64
import json

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

H = {"X-Codepilot": "1"}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9a"
                       "wAAAABJRU5ErkJggg==")
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 20
GIF = b"GIF89a" + b"\0" * 20
WEBP = b"RIFF\0\0\0\0WEBPVP8 " + b"\0" * 10


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
