"""Serving workspace images for Markdown previews: images only, inside the workspace, never scriptable."""

import base64

from fakes import FakeLLM
from starlette.testclient import TestClient

from codepilot.agent import Agent
from codepilot.server import create_app

H = {"X-Codepilot": "1"}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9a"
                       "wAAAABJRU5ErkJggg==")


def test_raw_images_only_and_sandboxed(cfg, store, repo, tmp_path):
    (repo / "docs").mkdir()
    (repo / "docs" / "arch.png").write_bytes(PNG)
    (repo / "docs" / "evil.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    (tmp_path / "outside.png").write_bytes(PNG)
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    r = client.get(f"/api/sessions/{sid}/raw?path=docs/arch.png")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    svg = client.get(f"/api/sessions/{sid}/raw?path=docs/evil.svg")
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert "sandbox" in svg.headers["content-security-policy"] and svg.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/api/sessions/{sid}/raw?path=agent/core.py").status_code == 415  # not an image
    assert client.get(f"/api/sessions/{sid}/raw?path=../outside.png").status_code == 404  # outside the workspace
