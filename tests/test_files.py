"""The user's own file operations (explorer and editor): create, rename, delete/restore, save."""

import os

import pytest
from fakes import FakeLLM
from starlette.testclient import TestClient

from codepilot.agent import Agent
from codepilot.server import create_app

H = {"X-Codepilot": "1"}


@pytest.fixture
def fs(cfg, store, repo):
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]

    def call(**body):
        return client.post(f"/api/sessions/{sid}/fs", json=body, headers=H)

    call.client, call.sid = client, sid
    return call


def test_new_file_and_folder(fs, repo):
    r = fs(op="new_file", path="agent/sub/new.py", content="x = 1\n")
    assert r.status_code == 200 and r.json()["path"] == "agent/sub/new.py"
    assert (repo / "agent/sub/new.py").read_text() == "x = 1\n"  # parents created
    assert fs(op="new_folder", path="docs/guides").json()["dir"]
    assert (repo / "docs/guides").is_dir()
    assert fs(op="new_file", path="agent/core.py").status_code == 409  # never overwrites
    assert fs(op="new_folder", path="docs").status_code == 409


def test_rename_and_collisions(fs, repo):
    assert fs(op="rename", path="agent/core.py", to="agent/calc.py").json()["path"] == "agent/calc.py"
    assert (repo / "agent/calc.py").exists() and not (repo / "agent/core.py").exists()
    assert fs(op="rename", path="agent/calc.py", to="tests/test_core.py").status_code == 409
    assert fs(op="rename", path="agent", to="lib/agent").json()["dir"]  # moves folders, creating parents
    assert (repo / "lib/agent/calc.py").exists()
    assert fs(op="rename", path="nope.py", to="x.py").status_code == 404


def test_delete_goes_to_trash_and_restores(fs, repo, cfg):
    d = fs(op="delete", path="agent").json()
    assert not (repo / "agent").exists() and (cfg.home / "trash" / d["trash_id"] / "item" / "core.py").exists()
    assert fs(op="restore", trash_id=d["trash_id"]).json()["path"] == "agent"
    assert (repo / "agent/core.py").read_text().startswith("def add")
    assert fs(op="restore", trash_id=d["trash_id"]).status_code == 404  # already restored

    d = fs(op="delete", path="Makefile").json()
    (repo / "Makefile").write_text("new\n")
    assert fs(op="restore", trash_id=d["trash_id"]).status_code == 409  # never clobbers a new file
    assert fs(op="restore", trash_id="../../etc").status_code == 400


def test_save_detects_changes_on_disk(fs, repo):
    opened = fs.client.get(f"/api/sessions/{fs.sid}/files?path=agent/core.py").json()
    r = fs(op="save", path="agent/core.py", content="def add(a, b):\n    return a + b\n", base_mtime=opened["mtime"])
    assert r.status_code == 200 and "a + b" in (repo / "agent/core.py").read_text()
    stale = fs(op="save", path="agent/core.py", content="mine\n", base_mtime=opened["mtime"])
    assert stale.status_code == 409 and "changed on disk" in stale.json()["error"]
    forced = fs(op="save", path="agent/core.py", content="mine\n", base_mtime=opened["mtime"], force=True)
    assert forced.status_code == 200
    assert (repo / "agent/core.py").read_text() == "mine\n"
    assert fs(op="save", path="agent", content="x").status_code == 400  # a folder


@pytest.mark.parametrize("bad", ["../escape.py", "agent/../../escape.py", "~/escape.py", ".", "", "a//b"])
def test_paths_must_stay_inside_the_workspace(fs, repo, bad):
    assert fs(op="new_file", path=bad).status_code == 400
    assert not (repo.parent / "escape.py").exists()


def test_cannot_delete_or_rename_the_workspace_itself(fs, repo):
    for path in (".", "/", ""):
        assert fs(op="delete", path=path).status_code == 400
    assert repo.exists()


def test_symlinks_act_on_the_link_not_the_target(fs, repo, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me\n")
    os.symlink(outside, repo / "link.txt")
    assert fs(op="save", path="link.txt", content="pwned\n").status_code == 400  # target is outside
    assert fs(op="delete", path="link.txt").status_code == 200
    assert outside.read_text() == "keep me\n" and not (repo / "link.txt").is_symlink()
    os.symlink(repo / "agent", repo / "agent_link")
    assert fs(op="delete", path="agent_link").status_code == 200
    assert (repo / "agent/core.py").exists()  # deleting a link to a folder keeps the folder


def test_requires_csrf_header(fs):
    r = fs.client.post(f"/api/sessions/{fs.sid}/fs", json={"op": "new_file", "path": "x.py"})
    assert r.status_code == 403


def test_listing_a_symlinked_folder_names_children_under_the_requested_path(fs, repo):
    """A link back to an ancestor used to list its children under their real paths, so the explorer saw a folder
    that contained itself and recursed until the tab crashed."""
    os.symlink(repo, repo / "loop")
    client, sid = fs.client, fs.sid
    root = client.get(f"/api/sessions/{sid}/files", params={"path": "."}).json()
    assert "loop" in [e["path"] for e in root["entries"]]
    inside = client.get(f"/api/sessions/{sid}/files", params={"path": "loop"}).json()
    paths = [e["path"] for e in inside["entries"]]
    assert paths and all(p.startswith("loop/") for p in paths), paths
    deeper = client.get(f"/api/sessions/{sid}/files", params={"path": "loop/loop"}).json()
    assert all(e["path"].startswith("loop/loop/") for e in deeper["entries"])
