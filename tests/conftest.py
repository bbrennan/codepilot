import json
import subprocess
from dataclasses import replace

import pytest

from codepilot.config import Config
from codepilot.store import Store


from fakes import FakeLLM, tool_use  # noqa: F401  (re-exported for older imports)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "target"
    (root / "agent").mkdir(parents=True)
    (root / "agent" / "core.py").write_text("def add(a, b):\n    return a - b\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_core.py").write_text(
        "from agent.core import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    (root / "traces").mkdir()
    spans = [
        {"traceId": "t-1", "spanId": "a", "name": "invoke_agent", "startTimeUnixNano": 1_700_000_000_000_000_000,
         "endTimeUnixNano": 1_700_000_002_000_000_000, "status": {"code": "OK"}},
        {"traceId": "t-1", "spanId": "b", "parentSpanId": "a", "name": "tool.search_products",
         "startTimeUnixNano": 1_700_000_000_500_000_000, "endTimeUnixNano": 1_700_000_001_000_000_000,
         "status": {"code": "ERROR", "message": "timeout"}, "attributes": {"query": "red shoes"}},
    ]
    (root / "traces" / "journey_1.json").write_text(json.dumps({"journey": "j1", "spans": spans}))
    (root / "traces" / "run.jsonl").write_text("\n".join(json.dumps(s) for s in spans) + "\n")
    (root / "Makefile").write_text("eval-bedrock:\n\techo eval\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid")):  # CI has no global identity
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    return root


def make_git_repo(root):
    """root as a repository with one commit of everything in it, as CI can make it: an invented identity and no
    signing, set in that repository only (CI has no identity; a developer's own config mustn't decide a test)."""
    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    if not (root / ".git").exists():
        git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/main")
    for key, value in (("user.name", "Ada Example"), ("user.email", "ada@example.invalid"),
                       ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        git("config", key, value)
    git("add", "-A")
    git("commit", "-q", "-m", "start")
    return root


@pytest.fixture
def git_isolated(tmp_path, monkeypatch):
    """No global or system git config reaches git in this test (an identity, signing, hooks, status settings): git
    runs in this process and in the in-process servers' threads, so the environment is enough."""
    empty = tmp_path / "empty.gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def git_repo(repo, git_isolated):
    """The sample repo, committed: what the Changes view's actions work on."""
    return make_git_repo(repo)


@pytest.fixture
def cfg(tmp_path):
    base = Config.from_env()
    return replace(base, provider="bedrock", home=tmp_path / "home", trace_dirs=[], log_groups=[],
                   test_cmd="python -c \"print('tests-ran')\"", eval_cmd="make eval-bedrock",
                   auto_approve_tests=False, context_tokens=None, max_steps=10)


@pytest.fixture
def store(cfg):
    return Store(cfg.home)


@pytest.fixture(autouse=True)
def no_registry_lookups(monkeypatch):
    """Tests never reach PyPI, npm or crates.io; a test that needs answers replaces this."""
    from codepilot import deps_guard

    def offline(url, timeout):
        raise OSError("no network in tests")

    monkeypatch.setattr(deps_guard, "_get", offline)
    deps_guard.CACHE.clear()
