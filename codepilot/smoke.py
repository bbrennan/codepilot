"""`codepilot smoke`: an end-to-end check of the configured provider with a real model.

`doctor` checks that each model answers a one-line request. This goes further: in a throwaway repo it runs
a full agent turn and checks streaming, tool calls (read_file, then propose_edit with the right fix), and
whether the model can read an image. Use it after setting up any provider (Bedrock, Anthropic, OpenAI or
Ollama) or changing models. It costs a few thousand tokens.
"""

from __future__ import annotations

import struct
import tempfile
import time
import zlib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .config import Config

OK, WARN, FAIL = "\033[32mpass\033[0m", "\033[33mwarn\033[0m", "\033[31mFAIL\033[0m"


def red_square(size: int = 48) -> bytes:
    """A small solid-red PNG, built without an imaging library."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    row = b"\x00" + b"\xd0\x10\x10" * size
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * size)) + chunk(b"IEND", b""))


def run(cfg: Config, tier: str = "main", vision: bool = True, progress: Callable[[str], None] = print,
        llm=None) -> int:
    from . import images
    from .agent import Agent
    from .store import Store

    failures = 0

    def line(status: str, label: str, detail: str = "") -> None:
        progress(f"  [{status}] {label}" + (f": {detail}" if detail else ""))

    with tempfile.TemporaryDirectory(prefix="codepilot-smoke-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        test_cfg = replace(cfg, home=Path(tmp) / "home", auto_apply_edits=False, max_steps=8)
        store = Store(test_cfg.home)
        agent = Agent(test_cfg, store, llm=llm)
        sess = store.create_session(str(repo), tier)
        progress(f"smoke test: {cfg.provider}, tier {tier} ({agent._model_for(sess)})")

        started = time.monotonic()
        events = list(agent.chat(sess.id, "calc.py has a bug: add() subtracts. Read calc.py, then use "
                                          "propose_edit to fix it. Don't run anything. Reply in one sentence."))
        seconds = time.monotonic() - started
        errors = [e["message"] for e in events if e["type"] == "error"]
        if errors:
            line(FAIL, "model call", errors[0][:300])
            return 1
        line(OK, "model call", f"{seconds:.1f}s")
        if any(e["type"] == "text" for e in events):
            line(OK, "streaming text")
        else:
            line(WARN, "streaming text", "no text was streamed (the reply may have been tool calls only)")
        tools = [e["name"] for e in events if e["type"] == "tool_call"]
        if tools:
            line(OK, "tool calls", ", ".join(tools))
        else:
            failures += 1
            line(FAIL, "tool calls", "the model didn't call any tools; it may not support tool use")
        props = store.list_proposals(sess.id)
        if any("a + b" in p.new_text for p in props):
            line(OK, "proposed the right fix", props[0].path)
        else:
            failures += 1
            line(FAIL, "proposed the right fix",
                 f"{len(props)} proposal(s), none changing it to a + b" if props else "no propose_edit call")
        usage = store.usage(sess.id)["by_model"]
        tokens = sum((u["input"] or 0) + (u["output"] or 0) for u in usage)
        line(OK, "token accounting", f"{tokens:,} tokens over {sum(u['calls'] for u in usage)} call(s)")

        if vision:
            sess2 = store.create_session(str(repo), tier)
            events = list(agent.chat(sess2.id, "What colour is this square? Answer with one word.",
                                     pasted=[images.block(red_square())]))
            reply = "".join(e.get("text", "") for e in events if e["type"] == "text").lower()
            errs = [e["message"] for e in events if e["type"] == "error"]
            if "red" in reply:
                line(OK, "reads images")
            else:
                line(WARN, "reads images", (errs[0][:200] if errs else f"answered {reply.strip()[:60]!r}") +
                     " (this model may not support images; everything else still works)")
    progress("smoke test passed" if not failures else f"smoke test: {failures} check(s) failed")
    return 1 if failures else 0
