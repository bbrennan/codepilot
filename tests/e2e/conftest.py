"""Browser tests: the real UI against a real server, with a scripted model instead of a provider.

Run with `make e2e` (first time: `make e2e-setup` to download Playwright's Chromium). Each test gets a fresh
server, database and browser context, and fails if the page logs a JavaScript error.
Set CODEPILOT_E2E_HEADED=1 to watch, or CODEPILOT_E2E_SLOWMO=250 to slow it down.
"""

from __future__ import annotations

import copy
import json
import os
import re
import socket
import threading
import time
from dataclasses import replace

import pytest

playwright_api = pytest.importorskip("playwright.sync_api", reason="pip install playwright (make e2e-setup)")

from codepilot import models  # noqa: E402
from codepilot.agent import Agent  # noqa: E402
from codepilot.server import create_app  # noqa: E402



def pytest_collection_modifyitems(items):
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


SPEC_DOCS = {
    "requirements": "# Requirements\n\n## 1. Export\n\nAs a user, I want CSV export, so that I can use Excel.\n\n"
                    "1.1 WHEN the user clicks Export THEN the system SHALL download a CSV file.\n",
    "design": "# Design\n\n## Overview\n\nA write_csv function in agent/csv.py (requirement 1.1).\n",
    "tasks": "# Tasks\n\n- [ ] 1. Add write_csv\n  - agent/csv.py\n  - _Requirements: 1.1_\n"
             "- [ ] 2. Add a test\n  - _Requirements: 1.1_\n",
}


class ScriptedLLM:
    """A deterministic stand-in for the model, driven by what the user typed."""

    def __init__(self):
        self.calls = []

    def stream(self, model, system, messages, tools=None, max_tokens=None):
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), "system": system})  # as sent, not as it grows
        last = messages[-1]["content"]
        user_text = " ".join(b.get("text", "") for b in last if "text" in b).split("<turn_context>")[0].lower()
        n = len(self.calls)
        full = " ".join(b.get("text", "") for b in last if "text" in b)
        phase = re.search(r'<spec name="[^"]+" kind="\w+" phase="(\w+)"', full)
        task = re.search(r"implement task ([\d.]+)", user_text)
        if any("toolResult" in b for b in last):
            content = [{"text": "Please review it in the Spec tab." if phase else "Done."}]
        elif phase and phase.group(1) == "implement" and task:
            content = [{"toolUse": {"toolUseId": f"t{n}", "name": "update_task",
                                    "input": {"task": task.group(1), "status": "done"}}}]
        elif phase and phase.group(1) != "implement":
            doc = phase.group(1)
            content = [{"toolUse": {"toolUseId": f"t{n}", "name": "write_spec",
                                    "input": {"doc": doc, "content": SPEC_DOCS[doc]}}}]
        elif "slow tool" in user_text:  # a step that takes a while, then a read-only tool: a turn you can steer
            time.sleep(1.5)
            content = [{"toolUse": {"toolUseId": f"t{n}", "name": "read_file", "input": {"path": "agent/core.py"}}}]
        elif "long command" in user_text:  # a plan, then a 30-line script waiting for approval
            script = "python - <<'EOF'\n" + "\n".join(f"print('step {i}')" for i in range(30)) + "\nEOF"
            content = [{"toolUse": {"toolUseId": f"p{n}", "name": "update_plan", "input": {"items": [
                {"text": f"Step {i} of the plan", "status": "todo"} for i in range(1, 9)]}}},
                {"toolUse": {"toolUseId": f"t{n}", "name": "run_command", "input": {"command": script}}}]
        elif "run python" in user_text:
            content = [{"toolUse": {"toolUseId": f"t{n}", "name": "run_command",
                                    "input": {"command": "python -c \"print('ran-' + str(6*7))\""}}}]
        elif "run ls" in user_text:
            content = [{"toolUse": {"toolUseId": f"t{n}", "name": "run_command", "input": {"command": "ls"}}}]
        elif "fix two" in user_text:
            content = [
                {"toolUse": {"toolUseId": f"t{n}a", "name": "propose_edit", "input": {
                    "path": "agent/core.py", "old_text": "a - b", "new_text": "a + b", "reason": "add should add"}}},
                {"toolUse": {"toolUseId": f"t{n}b", "name": "propose_edit", "input": {
                    "path": "tests/test_core.py", "old_text": "== 3", "new_text": "== 3  # 1 + 2",
                    "reason": "explain"}}}]
        elif "fix" in user_text:
            content = [{"toolUse": {"toolUseId": f"t{len(self.calls)}", "name": "propose_edit", "input": {
                "path": "agent/core.py", "old_text": "a - b", "new_text": "a + b", "reason": "add should add"}}}]
        elif "slow" in user_text:
            content = [{"text": "Thinking slowly. " * 8}]
        else:
            content = [{"text": "**Hello** from the scripted model.\n\n```python\nprint('hi')\n```\n\nSee "
                                "`agent/core.py:2`."}]
        for block in content:
            if "text" in block:
                for word in re.findall(r"\S+\s*", block["text"]):
                    if "slow" in user_text:
                        time.sleep(0.5 if "very slow" in user_text else 0.15)
                    yield {"type": "text", "text": word}
        sent = len(json.dumps(system)) + len(json.dumps(messages)) + len(json.dumps(tools or []))
        yield {"type": "message", "content": content,
               "stop_reason": "tool_use" if any("toolUse" in b for b in content) else "end_turn",
               "usage": {"inputTokens": sent // 3, "outputTokens": 40}}

    def complete(self, model, system, prompt, max_tokens=4000):
        return "SUMMARY: we fixed the add bug in agent/core.py."


class LiveServer:
    def __init__(self, app):
        import uvicorn

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.app = app
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 15
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("server didn't start")
            time.sleep(0.05)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)


def _fake_models(cfg):
    """Seed the model cache: models on the account (an older Sonnet, and Opus 5.5 reachable two ways) and one
    waiting for onboarding."""
    def probe(_cfg, model):
        return (False, "AccessDeniedException: model access is pending onboarding") if "haiku-5-5" in model \
            else (True, "ok")

    models.discover(cfg, refresh=True, probe=probe, lister=lambda _cfg: [
        "anthropic.claude-sonnet-5-5", "anthropic.claude-opus-5-5", "anthropic.claude-haiku-5-5",
        "anthropic.claude-haiku-4-5", "us.anthropic.claude-sonnet-4-5-20250929-v1:0", "global.anthropic.claude-opus-5-5"])


@pytest.fixture
def server(cfg, store, repo):
    cfg = replace(cfg, github=False, models={
        "fast": "anthropic.claude-haiku-5-5", "main": "anthropic.claude-sonnet-5-5",
        "hard": "anthropic.claude-opus-5-5"})
    _fake_models(cfg)
    llm = ScriptedLLM()
    app = create_app(cfg, store, Agent(cfg, store, llm=llm))
    app.state.terminals.shell = "/bin/sh"
    live = LiveServer(app)
    live.store, live.repo, live.llm, live.cfg = store, repo, llm, cfg
    yield live
    live.stop()


@pytest.fixture(scope="session")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=not os.environ.get("CODEPILOT_E2E_HEADED"),
                                  slow_mo=int(os.environ.get("CODEPILOT_E2E_SLOWMO", "0")))
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium for Playwright isn't installed (make e2e-setup): {str(exc).splitlines()[0]}")
        yield b
        b.close()


@pytest.fixture
def page(browser, server):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, base_url=server.url)
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=server.url)
    pg = context.new_page()
    pg.set_default_timeout(10_000)
    errors: list[str] = []
    pg.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    pg.on("console", lambda msg: errors.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None)
    pg.errors = errors
    pg.expected_errors = []  # substrings of console errors a test causes on purpose, e.g. "409 (Conflict)"
    yield pg
    context.close()
    errors = [e for e in errors if not any(x in e for x in pg.expected_errors)]
    assert not errors, "JavaScript errors in the page:\n" + "\n".join(errors)


@pytest.fixture
def session(server):
    """A session already pointed at the sample repo, so the UI opens straight into it."""
    return server.store.create_session(str(server.repo), "main")
