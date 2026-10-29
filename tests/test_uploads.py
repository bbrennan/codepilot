"""Files dragged into the explorer are saved inside the workspace, never outside it and never over something by accident."""

import os

import pytest
from fakes import FakeLLM
from starlette.testclient import TestClient

from codepilot import uploads
from codepilot.agent import Agent
from codepilot.server import create_app

H = {"X-Codepilot": "1"}


@pytest.fixture
def up(cfg, store, repo):
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]

    def call(path, body=b"data", replace=False, headers=H):
        q = {"path": path, **({"replace": "1"} if replace else {})}
        return client.put(f"/api/sessions/{sid}/upload", params=q, content=body, headers=headers)

    return call


def test_saves_binary_content_and_creates_parents(up, repo):
    blob = bytes(range(256)) * 10
    r = up("assets/img/logo.bin", blob)
    assert r.status_code == 200 and r.json()["path"] == "assets/img/logo.bin"
    assert (repo / "assets/img/logo.bin").read_bytes() == blob


def test_never_overwrites_unless_asked(up, repo):
    (repo / "keep.txt").write_text("mine")
    r = up("keep.txt", b"theirs")
    assert r.status_code == 409 and (repo / "keep.txt").read_text() == "mine"
    assert up("keep.txt", b"theirs", replace=True).status_code == 200
    assert (repo / "keep.txt").read_bytes() == b"theirs"


def test_a_folder_in_the_way_is_never_replaced(up, repo):
    (repo / "agent").mkdir(exist_ok=True)
    assert up("agent", b"x", replace=True).status_code == 409


@pytest.mark.parametrize("bad", ["../escape.txt", "a/../../escape.txt", "/etc/escape.txt", "~/escape.txt", "", "a//b.txt",
                                 "./x.txt", ".git/hooks/pre-commit", "sub/.git/config"])
def test_paths_must_stay_inside_the_workspace_and_out_of_git(up, repo, bad):
    assert up(bad).status_code == 400
    assert not (repo.parent / "escape.txt").exists()


def test_a_symlink_cannot_lead_out_of_the_workspace(up, repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, repo / "link")
    assert up("link/pwn.txt").status_code == 400
    os.symlink(outside / "target.txt", repo / "lnk.txt")
    assert up("lnk.txt", replace=True).status_code in (400, 409)
    assert not list(outside.iterdir())


def test_too_large_is_refused_and_leaves_nothing_behind(up, repo, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 10)
    r = up("big.bin", b"x" * 11)
    assert r.status_code == 413 and not (repo / "big.bin").exists()


def test_needs_the_csrf_header(up, repo):
    assert up("x.txt", headers={}).status_code == 403
    assert not (repo / "x.txt").exists()


def test_no_temporary_files_remain(up, repo):
    before = set(os.listdir(repo))
    up("ok.txt", b"1")
    assert set(os.listdir(repo)) - before == {"ok.txt"}
