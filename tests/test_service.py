"""Running codepilot without a terminal: start/stop/status, the macOS launcher, quieter logs."""

import json
import logging
import os
import plistlib
import socket
import sys
from dataclasses import replace

import pytest

from codepilot import cli, service
from codepilot.models import _worth_probing


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_start_status_stop_a_real_background_server(cfg, monkeypatch, capsys):
    monkeypatch.setenv("TERM", "xterm")  # as if run from a terminal: inherit this environment
    monkeypatch.setenv("CODEPILOT_PROVIDER", "ollama")
    monkeypatch.setenv("CODEPILOT_HOME", str(cfg.home))
    cfg = replace(cfg, provider="ollama", port=free_port())
    try:
        assert service.start(cfg, None, open_ui=False) == 0
        info = service.running(cfg)
        assert info and service.is_up(info["url"]) and str(cfg.port) in info["url"]
        assert service.start(cfg, None, open_ui=False) == 0  # idempotent: doesn't start a second one
        assert "already running" in capsys.readouterr().out
        assert service.status(cfg) == 0
        assert "codepilot: provider=ollama" in (cfg.home / "server.log").read_text()  # unbuffered log
    finally:
        assert service.stop(cfg) == 0
    assert service.running(cfg) is None and not service.is_up(f"http://127.0.0.1:{cfg.port}")
    assert service.status(cfg) == 3


def test_stale_pid_file_is_cleaned_up(cfg):
    cfg.home.mkdir(parents=True, exist_ok=True)
    (cfg.home / "server.pid").write_text(json.dumps({"pid": 999_999, "url": "http://127.0.0.1:1", "env": "",
                                                     "started": 0}))
    assert service.running(cfg) is None and not (cfg.home / "server.pid").exists()


def test_failed_start_reports_the_log(cfg, monkeypatch, capsys):
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("CODEPILOT_PROVIDER", "nonsense")  # config error: the child exits at once
    cfg = replace(cfg, port=free_port())
    assert service.start(cfg, None, open_ui=False, wait=10) == 1
    assert "failed to start" in capsys.readouterr().err and service.running(cfg) is None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS app bundle")
def test_app_bundle(cfg, tmp_path):
    env = tmp_path / "work.env"
    env.write_text("CODEPILOT_PROVIDER=ollama\n")
    assert service.install_app(cfg, env, tmp_path) == 0
    app = tmp_path / "Codepilot.app" / "Contents"
    plist = plistlib.loads((app / "Info.plist").read_bytes())
    assert plist["CFBundleExecutable"] == "Codepilot" and plist["CFBundleIconFile"] == "codepilot"
    launcher = (app / "MacOS" / "Codepilot").read_text()
    assert f'"{sys.executable}" -m codepilot --env-file "{env}" start' in launcher
    assert os.access(app / "MacOS" / "Codepilot", os.X_OK) and (app / "Resources" / "codepilot.icns").stat().st_size
    assert service.install_app(cfg, None, tmp_path) == 0  # re-running replaces it cleanly
    assert "--env-file" not in (app / "MacOS" / "Codepilot").read_text()


def test_shell_environment_recovers_login_path(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = service.shell_environment()
    assert env.get("PATH") and "PWD" not in env


@pytest.mark.parametrize("profile,region,probe", [
    ("us.anthropic.claude-sonnet-4-5-20250929-v1:0", "us-east-1", True),
    ("global.anthropic.claude-opus-4-5-20251101-v1:0", "us-west-2", True),
    ("eu.anthropic.claude-sonnet-4-5-20250929-v1:0", "us-east-1", False),  # another geography
    ("us.anthropic.claude-3-5-haiku-20241022-v1:0", "us-east-1", False),  # legacy
    ("apac.anthropic.claude-sonnet-4-5-20250929-v1:0", "ap-southeast-2", True),
    ("us.anthropic.claude-sonnet-4-20250514-v1:0", "us-east-1", False),  # retired by Anthropic
    ("us.anthropic.claude-sonnet-4-6", "us-east-1", True),
    ("us.meta.llama3-1-70b-instruct-v1:0", "us-east-1", False),
])
def test_only_relevant_inference_profiles_are_probed(profile, region, probe):
    assert _worth_probing(profile, region) is probe


def test_per_request_library_logs_are_quiet(monkeypatch, cfg):
    monkeypatch.delenv("CODEPILOT_VERBOSE", raising=False)
    monkeypatch.setenv("CODEPILOT_HOME", str(cfg.home))
    cli.main(["status"])
    for name in ("httpx", "botocore", "anthropic"):
        assert logging.getLogger(name).level == logging.WARNING


def test_start_restarts_a_server_running_older_code(cfg, monkeypatch, capsys):
    from codepilot import version

    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("CODEPILOT_PROVIDER", "ollama")
    monkeypatch.setenv("CODEPILOT_HOME", str(cfg.home))
    cfg = replace(cfg, provider="ollama", port=free_port())
    try:
        assert service.start(cfg, None, open_ui=False) == 0
        first = service.running(cfg)["pid"]
        assert service.start(cfg, None, open_ui=False) == 0  # same code: just reopens
        assert service.running(cfg)["pid"] == first
        monkeypatch.setattr(version, "fingerprint", lambda: "after-git-pull")  # the code on disk changed
        assert service.start(cfg, None, open_ui=False) == 0
        assert "restarting it" in capsys.readouterr().out
        info = service.running(cfg)
        assert info["pid"] != first and service.is_up(info["url"])
        assert info["version"] == version.STARTED  # the new server records the code it actually loaded
    finally:
        service.stop(cfg)


def test_server_restarts_itself_in_place(cfg, monkeypatch):
    import json
    import time
    import urllib.request

    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("CODEPILOT_PROVIDER", "ollama")
    monkeypatch.setenv("CODEPILOT_HOME", str(cfg.home))
    cfg = replace(cfg, provider="ollama", port=free_port())
    try:
        assert service.start(cfg, None, open_ui=False) == 0
        info = service.running(cfg)
        config = json.loads(urllib.request.urlopen(info["url"] + "/api/config").read())
        assert config["stale"] is False and config["version"]
        req = urllib.request.Request(info["url"] + "/api/restart", method="POST", headers={"X-Codepilot": "1"})
        assert urllib.request.urlopen(req).status == 202
        time.sleep(1.0)
        deadline = time.time() + 20
        while not service.is_up(info["url"]) and time.time() < deadline:
            time.sleep(0.2)
        assert service.is_up(info["url"]) and service.running(cfg)["pid"] == info["pid"]  # same process, new code
    finally:
        service.stop(cfg)


# -- the app window has its own browser profile ---------------------------------------------------------------------


def _launches(monkeypatch, platform):
    """What open_window would run, with every browser installed."""
    calls = []
    monkeypatch.setattr(service.sys, "platform", platform)
    monkeypatch.setattr(service.subprocess, "run", lambda argv, **kw: type("Done", (), {"returncode": 0})())
    monkeypatch.setattr(service.subprocess, "Popen", lambda argv, **kw: calls.append(argv))
    monkeypatch.setattr(service.shutil, "which", lambda exe: f"/usr/bin/{exe}")
    monkeypatch.delenv("CODEPILOT_APP_BROWSER", raising=False)
    return calls


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_the_app_window_opens_in_its_own_browser_profile(cfg, monkeypatch, platform):
    """No extensions in the page, and a window position of its own (per display), apart from your everyday browsing."""
    calls = _launches(monkeypatch, platform)
    monkeypatch.delenv("CODEPILOT_APP_PROFILE", raising=False)
    service.open_window("http://127.0.0.1:8765", profile=service.app_profile(cfg))
    argv = calls[0]
    assert "--app=http://127.0.0.1:8765" in argv and f"--user-data-dir={cfg.home / 'chrome'}" in argv
    assert "--no-first-run" in argv and "--no-default-browser-check" in argv


def test_codepilot_app_profile_0_keeps_your_everyday_profile(cfg, monkeypatch):
    calls = _launches(monkeypatch, "darwin")
    monkeypatch.setenv("CODEPILOT_APP_PROFILE", "0")
    assert service.app_profile(cfg) is None
    service.open_window("http://127.0.0.1:8765", profile=service.app_profile(cfg))
    assert not any(a.startswith("--user-data-dir") for a in calls[0])


def test_start_opens_the_window_in_the_app_profile(cfg, monkeypatch):
    seen = []
    monkeypatch.delenv("CODEPILOT_APP_PROFILE", raising=False)
    monkeypatch.setattr(service, "running", lambda cfg: None)
    monkeypatch.setattr(service, "is_up", lambda url: True)  # already serving: start just opens the window
    monkeypatch.setattr(service, "server_stale", lambda url: False)
    monkeypatch.setattr(service, "open_window", lambda url, app_window=True, profile=None: seen.append(profile))
    assert service.start(cfg, None) == 0
    assert seen == [cfg.home / "chrome"]
