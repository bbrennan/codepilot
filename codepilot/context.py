"""Context-window management: keep long sessions and long tasks inside the model's window.

Modelled on what the strongest coding agents do (Claude Code, Codex CLI, OpenCode, Cline, OpenHands):

1. **Measure in tokens, before every model call.** Each reply's real prompt-token count calibrates a
   tokens-per-character ratio, so the next request's size is estimated accurately, mid-task included.
   The budget is the model's window minus the reply reserve (Codex uses the same formula).
2. **Tier 1, pruning ("micro-compaction"):** at `CODEPILOT_PRUNE_AT` of the budget, bulky old tool outputs
   are replaced by one-line stubs, outside a protected zone of recent context. It runs only if it frees a
   worthwhile amount (OpenCode: >20k tokens, protecting the last 40k). It needs no model call.
3. **Tier 2, summarising:** at `CODEPILOT_COMPACT_AT`, earlier turns are folded into one structured,
   rewritten summary (rewriting avoids summary-of-summary drift). The current turn and the previous one stay
   verbatim. Deterministic working state (the plan, proposals and their status, files touched, commands run)
   is carried over exactly, not paraphrased.
4. **Recovery:** if a provider still rejects a request as too long, prune hard, summarise everything but the
   current turn, and retry once.
5. **Manual control:** `/compact [focus]` in chat, plus "Compact now" and "Continue in new session" in the UI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Any

from . import prompts
from .bedrock import BedrockError
from .config import Config
from .store import Store

DEFAULT_TOKENS_PER_CHAR = 1 / 3.0  # conservative for code until a real reply calibrates it
MIN_CLEAR_CHARS = 800  # tool outputs shorter than this aren't worth clearing
NEVER_CLEAR = {"load_skill", "update_plan", "remember", "open_workspace"}
CLEARED_PREFIX = "[cleared to free context:"
TICKET = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d{2,6}\b")
FILE_LINE = re.compile(r"\b[\w./-]+\.[A-Za-z]{1,5}:\d+\b")
TRACE_ID = re.compile(r"\b(?:trc|trace|req|span|sess|run|job)[_-][A-Za-z0-9]{4,}\b")
TEST_RESULT = re.compile(r"\b\d+ (?:passed|failed|errors?|skipped)\b[^\n]{0,40}")
VERBATIM_HEADER = "User's messages (verbatim, in order):"
VERBATIM_CHARS = 6000  # about 1.5k tokens of the user's own words survive every compaction
CONSTRAINT = re.compile(r"\b(?:don'?t|do not|never|always|must|avoid|instead|prefer|make sure|only|"
                        r"should(?:n'?t)?)\b", re.IGNORECASE)
ERROR_LINE = re.compile(r"^.*\b(?:\w*Error|\w*Exception|FAILED|Traceback)\b.*$", re.MULTILINE)
CONTEXT_MARKERS = ("<turn_context>", "<attached_files>", "<skill ", "<steering ")
OVERFLOW = re.compile(
    r"too long|too many (?:input |total )?(?:tokens|text bytes)|context (?:length|window|limit)|maximum context|"
    r"prompt is too long|input length|context_length_exceeded|exceeds? (?:the )?(?:model'?s? )?(?:maximum|context)",
    re.IGNORECASE)


def is_overflow(error: Exception | str) -> bool:
    """Does this provider error mean the request didn't fit in the context window?"""
    return bool(OVERFLOW.search(str(error)))


IMAGE_CHARS = 1600 * 3  # an image costs ~1.6k tokens, not its byte size (see images.TOKENS_PER_IMAGE)


def _size_default(o: Any) -> str:
    if isinstance(o, (bytes, bytearray)):
        return "x" * (IMAGE_CHARS if len(o) > 2000 else len(o))
    return str(o)


def _chars(obj: Any) -> int:
    return len(json.dumps(obj, default=_size_default))


def _is_user_turn(m: dict) -> bool:
    return m["role"] == "user" and any("text" in b and not b["text"].startswith("<turn_context>")
                                       for b in m["content"])


def _unique(items) -> list[str]:
    seen: list[str] = []
    for i in items:
        if i not in seen:
            seen.append(i)
    return seen


def pick_verbatim(asks: list[str], budget: int = VERBATIM_CHARS) -> list[str]:
    """Which of the user's messages to keep word for word: the original task, the latest ten, then
    messages that state constraints or preferences (newest first), within a character budget."""
    n = len(asks)
    order = [0] + list(range(n - 1, max(0, n - 11), -1)) + \
        [i for i in range(n - 1, 0, -1) if CONSTRAINT.search(asks[i])]
    keep: set[int] = set()
    used = 0
    for i in order:
        if i < n and i not in keep and used + len(asks[i]) <= budget:
            keep.add(i)
            used += len(asks[i])
    return [asks[i] for i in sorted(keep)]


class ContextManager:
    def __init__(self, cfg: Config, store: Store, llm: Any, fast_model: Any = None):
        self.cfg = cfg
        self.store = store
        self.llm = llm
        self.fast_model = fast_model or (lambda: cfg.models["fast"])

    # -- budget ------------------------------------------------------------------------------------

    def window(self, model: str) -> int:
        return self.cfg.context_window(model)

    def budget(self, model: str) -> int:
        """Tokens available for the prompt: the window minus room for the reply."""
        reserve = min(self.cfg.max_tokens, 20000, 8192 if self.cfg.provider == "ollama" else 20000)
        return max(4000, self.window(model) - reserve)

    def _state(self, session_id: str) -> dict:
        return dict(self.store.get_session(session_id).context_state or {})

    def ratio(self, session_id: str) -> float:
        return float(self._state(session_id).get("tokens_per_char") or DEFAULT_TOKENS_PER_CHAR)

    def estimate(self, session_id: str, system: list[dict], specs: list[dict], messages: list[dict] | None = None
                 ) -> int:
        if messages is None:
            messages = self.store.live_messages(session_id)
        return int((_chars(system) + _chars(specs) + _chars(messages)) * self.ratio(session_id))

    def record(self, session_id: str, system: list[dict], specs: list[dict], messages: list[dict],
               usage: dict) -> None:
        """Calibrate the tokens-per-character ratio from a reply's real prompt size."""
        prompt = (usage.get("inputTokens") or 0) + (usage.get("cacheReadInputTokens") or 0) \
            + (usage.get("cacheWriteInputTokens") or 0)
        sent = _chars(system) + _chars(specs) + _chars(messages)
        if prompt <= 0 or sent <= 0:
            return
        state = self._state(session_id)
        measured = min(0.8, max(0.12, prompt / sent))
        old = state.get("tokens_per_char")
        state["tokens_per_char"] = measured if old is None else 0.5 * old + 0.5 * measured
        state["prompt_tokens"] = prompt
        self.store.update_session(session_id, context_state=state)

    def usage_view(self, session_id: str, model: str, system: list[dict], specs: list[dict]) -> dict:
        tokens = self.estimate(session_id, system, specs)
        budget = self.budget(model)
        return {"type": "context", "tokens": tokens, "budget": budget, "window": self.window(model),
                "prune_at": self.cfg.prune_at, "compact_at": self.cfg.compact_at,
                "has_summary": bool(self.store.get_session(session_id).summary)}

    # -- tier 1: prune old tool outputs ------------------------------------------------------------

    def prune(self, session_id: str, protect_tokens: int, min_free_tokens: int) -> tuple[int, int]:
        """Replace bulky tool outputs older than the protected recent zone with stubs.

        Returns (outputs cleared, tokens freed). Writes nothing unless at least `min_free_tokens` would be freed.
        """
        rows = self.store.messages(session_id)
        ratio = self.ratio(session_id)
        calls: dict[str, tuple[str, dict]] = {}
        for _, m in rows:
            for b in m["content"]:
                if "toolUse" in b:
                    calls[b["toolUse"]["toolUseId"]] = (b["toolUse"]["name"], b["toolUse"].get("input") or {})
        protect_chars = protect_tokens / ratio
        seen = 0
        edits: dict[int, list[dict]] = {}
        freed = 0
        cleared = 0
        for mid, m in reversed(rows):
            seen += _chars(m["content"])
            if seen <= protect_chars:
                continue
            new_content, changed = [], False
            for b in m["content"]:
                if "image" in b:  # old images go first: each costs as much as a page of text
                    new_content.append({"text": "[image removed to free context]"})
                    freed += IMAGE_CHARS
                    cleared += 1
                    changed = True
                    continue
                tr = b.get("toolResult")
                text = "\n".join(c.get("text", "") for c in tr.get("content", [])) if tr else ""
                name, inp = calls.get(tr["toolUseId"], ("tool", {})) if tr else ("", {})
                if tr and len(text) > MIN_CLEAR_CHARS and name not in NEVER_CLEAR and \
                        not text.startswith(CLEARED_PREFIX):
                    first = text.strip().splitlines()[0][:160] if text.strip() else ""
                    stub = (f"{CLEARED_PREFIX} {name}({json.dumps(inp)[:200]}) returned {len(text):,} chars, "
                            f"starting: {first!r}. Run the tool again if you need this output.]")
                    new_content.append({"toolResult": {**tr, "content": [{"text": stub}]}})
                    freed += len(text) - len(stub)
                    cleared += 1
                    changed = True
                else:
                    new_content.append(b)
            if changed:
                edits[mid] = new_content
        freed_tokens = int(freed * ratio)
        if not edits or freed_tokens < min_free_tokens:
            return 0, 0
        for mid, content in edits.items():
            self.store.replace_content(mid, content)
        return cleared, freed_tokens

    # -- tier 2: summarise earlier turns -----------------------------------------------------------

    def summarize(self, session_id: str, keep_turns: int = 2, focus: str = "") -> Generator[dict, None, bool]:
        """Fold everything before the last `keep_turns` user turns into the session summary."""
        rows = self.store.messages(session_id)
        starts = [i for i, (_, m) in enumerate(rows) if _is_user_turn(m)]
        if keep_turns <= 0:
            cut = len(rows)
        elif len(starts) > keep_turns:
            cut = starts[-keep_turns]
        else:
            return False
        old = rows[:cut]
        if not old:
            return False
        sess = self.store.get_session(session_id)
        yield {"type": "notice", "message": f"Compacting memory: summarising {len(old)} earlier messages"
                                            f"{' (focus: ' + focus + ')' if focus else ''}…"}
        state = self.working_state(session_id, [m for _, m in old], previous=sess.summary)
        from .agent import render_transcript  # local import: agent imports this module

        prompt = (f"Existing summary (rewrite it, don't append to it):\n{sess.summary or '(none)'}\n\n"
                  f"{'Focus requested by the user: ' + focus + chr(10) + chr(10) if focus else ''}"
                  f"Conversation to fold in:\n{render_transcript([m for _, m in old])}\n\n"
                  "Write the updated summary.")
        try:
            text = self.llm.complete(self.fast_model(), prompts.SUMMARIZE, prompt, max_tokens=3000)
        except BedrockError as exc:
            text = f"{sess.summary}\n\n(Automatic summary unavailable: {exc})".strip()
        summary = (text.strip() + ("\n\n" + state if state else "")).strip()
        self.store.update_session(session_id, summary=summary)
        self.store.archive_messages(session_id, [mid for mid, _ in old])
        return True

    def working_state(self, session_id: str, old_messages: list[dict], previous: str = "") -> str:
        """Exact, non-paraphrased state to carry across a compaction."""
        lines: list[str] = []
        plan = None
        files: list[str] = []
        commands: list[str] = []
        for _, m in self.store.messages(session_id, include_archived=True):
            for b in m["content"]:
                tu = b.get("toolUse")
                if tu and tu["name"] == "update_plan" and isinstance(tu.get("input", {}).get("items"), list):
                    plan = tu["input"]["items"]
        for m in old_messages:
            for b in m["content"]:
                tu = b.get("toolUse")
                if not tu:
                    continue
                inp = tu.get("input") or {}
                if tu["name"] in ("read_file", "propose_edit", "write_scratch", "trace_outline", "read_trace") \
                        and inp.get("path") and inp["path"] not in files:
                    files.append(str(inp["path"]))
                if tu["name"] in ("run_tests", "run_command", "run_checks"):
                    commands.append(f"{tu['name']} {inp.get('command') or inp.get('args') or inp.get('kind') or ''}"
                                    .strip())
        if plan:
            marks = {"done": "x", "doing": ">"}
            lines.append("Plan: " + "; ".join(f"[{marks.get(i.get('status'), ' ')}] {i.get('text', '')}"
                                              for i in plan))
        props = self.store.list_proposals(session_id)
        if props:
            lines.append("Proposals: " + "; ".join(f"#{p.id} {p.path} {p.status}" for p in props[-15:]))
        if files:
            lines.append("Files examined or changed earlier: " + ", ".join(files[-25:]))
        if commands:
            lines.append("Commands run earlier: " + "; ".join(commands[-10:]))
        # The user's own words carry their constraints and preferences, which summarisers most often drop.
        # Carry earlier verbatim messages forward too, so they survive repeated compactions.
        asks: list[str] = []
        for header in (VERBATIM_HEADER, "User's messages (verbatim, most recent last):"):
            if header in previous:
                asks += [ln[2:] for ln in previous.split(header, 1)[1].splitlines() if ln.startswith("> ")]
                break
        texts: list[str] = []
        for m in old_messages:
            for b in m["content"]:
                if "text" in b:
                    texts.append(b["text"])
                    if m["role"] == "user" and not b["text"].startswith(CONTEXT_MARKERS):
                        t = " ".join(b["text"].split())
                        if t and t not in asks:
                            asks.append(t[:500] + ("…" if len(t) > 500 else ""))
                elif "toolResult" in b:
                    texts += [c.get("text", "") for c in b["toolResult"].get("content", [])
                              if not c.get("text", "").startswith(CLEARED_PREFIX)]
                elif "toolUse" in b:
                    texts.append(json.dumps(b["toolUse"].get("input") or {}))
        blob = "\n".join(texts)
        ids = _unique(TICKET.findall(blob) + TRACE_ID.findall(blob) + FILE_LINE.findall(blob))[:25]
        errors = _unique(" ".join(e.split())[:200] for e in ERROR_LINE.findall(blob))[:6]
        if ids:
            lines.append("Key identifiers: " + ", ".join(ids))
        if errors:
            lines.append("Errors seen: " + " | ".join(errors))
        results = _unique(" ".join(t.split()) for t in TEST_RESULT.findall(blob))[-3:]
        if results:
            lines.append("Latest test results: " + " | ".join(results))
        out = ("Working state (exact, carried across compaction):\n- " + "\n- ".join(lines)) if lines else ""
        asks = pick_verbatim(asks)
        if asks:
            out += ("\n\n" if out else "") + VERBATIM_HEADER + "\n" + "\n".join(f"> {a}" for a in asks)
        if lines or asks:
            out += "\n(The full earlier conversation is archived; use the recall tool for exact details.)"
        return out

    # -- orchestration -----------------------------------------------------------------------------

    def ensure_room(self, session_id: str, model: str, system: list[dict], specs: list[dict]
                    ) -> Generator[dict, None, bool]:
        """Before a model call: prune, then summarise, if the request is getting close to the window."""
        budget = self.budget(model)
        est = self.estimate(session_id, system, specs)
        changed = False
        if est > self.cfg.prune_at * budget:
            cleared, freed = self.prune(session_id, protect_tokens=min(40000, int(budget * 0.25)),
                                        min_free_tokens=min(20000, int(budget * 0.08)))
            if cleared:
                changed = True
                yield {"type": "notice", "message": f"Freed ~{freed:,} tokens by clearing {cleared} old tool "
                                                    "outputs (the assistant can re-run tools if needed)."}
                est = self.estimate(session_id, system, specs)
        if est > self.cfg.compact_at * budget:
            changed = (yield from self.summarize(session_id, keep_turns=2)) or changed
            if self.estimate(session_id, system, specs) > self.cfg.compact_at * budget:
                changed = (yield from self.summarize(session_id, keep_turns=1)) or changed
        return changed

    def recover(self, session_id: str, model: str) -> Generator[dict, None, bool]:
        """After a 'prompt too long' error: shrink hard so the retry fits."""
        budget = self.budget(model)
        cleared, freed = self.prune(session_id, protect_tokens=min(8000, int(budget * 0.05)), min_free_tokens=0)
        if cleared:
            yield {"type": "notice", "message": f"Cleared {cleared} tool outputs (~{freed:,} tokens)."}
        summarized = yield from self.summarize(session_id, keep_turns=1)
        return bool(cleared or summarized)

    def compact_now(self, session_id: str, focus: str = "") -> Generator[dict, None, bool]:
        """Manual /compact: summarise the whole conversation so far."""
        cleared, _ = self.prune(session_id, protect_tokens=0, min_free_tokens=0)
        done = yield from self.summarize(session_id, keep_turns=0, focus=focus)
        if not done and not cleared:
            yield {"type": "notice", "message": "Nothing to compact yet."}
        return bool(done or cleared)
