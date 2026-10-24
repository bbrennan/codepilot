"""The agent loop: model <-> tools, with approval pauses, an explore sub-agent, and rolling-summary memory.

Every public method is a generator of UI events (dicts with a "type" key), so the web server and
the terminal REPL render the same stream.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections.abc import Callable, Generator, Iterator
from pathlib import Path
from typing import Any

from . import checks, images, mentions, models, modes, prompts, repomap, router, skills, specs, steering, webtools
from .bedrock import BedrockError, make_client
from .config import Config
from .context import CLEARED_PREFIX, ContextManager, is_overflow
from .store import Session, Store
from .tools import SKIP_DIRS, Tool, ToolContext, ToolError, build_tools, detect_test_cmd, execute, trace_roots

UI_OUTPUT_LIMIT = 6000
EXPLORE_MAX_STEPS = 12



def make_llm(cfg: Config) -> Any:
    if cfg.provider == "ollama":
        from .ollama import Ollama

        return Ollama(cfg)
    if cfg.provider == "anthropic":
        from .anthropic_api import AnthropicAPI

        return AnthropicAPI(cfg)
    if cfg.provider == "openai":
        from .openai_api import OpenAIAPI

        return OpenAIAPI(cfg)
    from .bedrock import BedrockRouter

    return BedrockRouter(cfg)


def is_user_turn(message: dict) -> bool:
    return message["role"] == "user" and any("text" in b for b in message["content"])


def arg_summary(tool_input: dict) -> str:
    for key in ("path", "pattern", "query", "command", "args", "task", "name", "log_group", "note"):
        if tool_input.get(key):
            return str(tool_input[key])[:160]
    return json.dumps(tool_input)[:160]


class Agent:
    def __init__(self, cfg: Config, store: Store, llm: Any | None = None,
                 logs_client_factory: Callable[[], Any] | None = None):
        self.cfg = cfg
        self.store = store
        self.llm = llm or make_llm(cfg)
        self.tools: dict[str, Tool] = {t.name: t for t in build_tools(cfg)}
        self._logs_client = None
        self._logs_factory = logs_client_factory or self._default_logs_client
        self._cancelled: set[str] = set()
        self._queues: dict[str, list[dict]] = {}  # messages typed while a turn runs, read at the next step
        self._queue_lock = threading.Lock()
        self.ctxm = ContextManager(cfg, store, self.llm, fast_model=lambda: self.tier_model("fast"))

    def cancel(self, session_id: str) -> list[str]:
        """Ask a running turn to stop at the next safe point. Returns queued messages, so the UI can put them
        back in the message box instead of losing them."""
        self._cancelled.add(session_id)
        return [q["text"] for q in self.take_queue(session_id)]

    # -- queued messages: typed while a turn runs ------------------------------------------------

    def enqueue(self, session_id: str, text: str) -> dict:
        item = {"id": uuid.uuid4().hex[:10], "text": text}
        with self._queue_lock:
            self._queues.setdefault(session_id, []).append(item)
        return item

    def dequeue(self, session_id: str, qid: str) -> bool:
        with self._queue_lock:
            items = self._queues.get(session_id, [])
            kept = [q for q in items if q["id"] != qid]
            self._queues[session_id] = kept
            return len(kept) != len(items)

    def take_queue(self, session_id: str) -> list[dict]:
        with self._queue_lock:
            return self._queues.pop(session_id, [])

    def queued(self, session_id: str) -> list[dict]:
        with self._queue_lock:
            return list(self._queues.get(session_id, []))

    def _deliver_queue(self, session_id: str) -> Iterator[dict]:
        """Mid-turn: add queued messages to the conversation before the next model call."""
        items = self.take_queue(session_id)
        if not items:
            return
        last = self.store.last_message(session_id)
        blocks = [{"text": QUEUED_PREFIX + q["text"]} for q in items]
        if last and last[1]["role"] == "user":
            self.store.replace_content(last[0], last[1]["content"] + blocks)
        else:
            self.store.add_message(session_id, "user", blocks)
        for q in items:  # part of a running turn, so no mid: it can't be edited or retried on its own
            yield {"type": "user", "text": q["text"], "queued_id": q["id"]}

    # -- rewind: edit an earlier message, or retry the last one ---------------------------------

    def rewind(self, session_id: str, mid: int, text: str, tier: str | None = None) -> Iterator[dict]:
        """Remove a user message and everything after it, then send `text` in its place."""
        if self.store.is_archived(mid):
            yield {"type": "error", "message": "That message was summarised when the conversation was compacted, "
                                               "so it can't be edited. Send a new message instead."}
            return
        target = next((msg for m, msg in self.store.messages(session_id) if m == mid), None)
        if not target or target["role"] != "user" or not target["content"] or "text" not in target["content"][0]:
            yield {"type": "error", "message": "Only a message that started a turn can be edited or retried."}
            return
        since = self.store.message_created(mid)
        self.store.delete_messages_from(session_id, mid)
        if since is not None:
            discarded = self.store.discard_pending_since(session_id, since)
            if discarded:
                yield {"type": "proposals_changed", "ids": discarded}
        state = dict(self.store.get_session(session_id).context_state or {})
        state["steering_loaded"] = []
        self.store.update_session(session_id, pending=None, context_state=state)
        yield from self.chat(session_id, text, tier)

    def _default_logs_client(self) -> Any:
        if self._logs_client is None:
            self._logs_client = make_client(self.cfg, "logs")
        return self._logs_client

    # -- public API -----------------------------------------------------------------------------

    def chat(self, session_id: str, text: str, tier: str | None = None, pasted: list[dict] | None = None
             ) -> Iterator[dict]:
        """`pasted`: image blocks the user pasted or dropped into the message box."""
        yield from self._chat_once(session_id, text, tier, pasted)
        yield from self._drain_queue_turns(session_id)

    def _drain_queue_turns(self, session_id: str) -> Iterator[dict]:
        """Messages queued too late for the turn that just ended start the next one, in the same stream."""
        while self.queued(session_id) and session_id not in self._cancelled \
                and not self.store.get_session(session_id).pending:
            items = self.take_queue(session_id)
            text = "\n\n".join(q["text"] for q in items)
            yield {"type": "user", "text": text, "queued_ids": [q["id"] for q in items]}
            yield from self._chat_once(session_id, text)

    def _chat_once(self, session_id: str, text: str, tier: str | None = None, pasted: list[dict] | None = None
                   ) -> Iterator[dict]:
        sess = self.store.get_session(session_id)
        self._cancelled.discard(session_id)
        if sess.pending:
            # Like Claude Code: writing instead of approving declines the waiting call(s), and your message goes
            # to the model with that decision.
            yield {"type": "notice", "message": "Declined the waiting command; your message goes to codepilot instead."}
            yield from self.resume(session_id, approve=False, feedback=text)
            return
        if tier and tier != sess.tier:
            self.store.update_session(session_id, tier=tier)
        stripped = text.strip()
        if stripped == "/compact" or stripped.startswith("/compact "):
            yield from self.compact(session_id, stripped[len("/compact"):].strip())
            return
        if not sess.title:
            self.store.update_session(session_id, title=text.strip().splitlines()[0][:80])
        content = [{"text": text}]
        root = self._ctx(sess).root
        slash = skills.slash_command(text, root, self.cfg.home)
        if slash:
            skill, rest = slash
            intro = f"The user invoked the /{skill.name} skill{': ' + rest if rest else ''}."
            content.append({"text": f'<skill name="{skill.name}">\n{intro} Follow these instructions:\n\n'
                                    f"{skill.body}\n</skill>"})
            yield {"type": "skill", "name": skill.name}
        block, labels = mentions.attachment_block(root, text)
        if block:
            content.append({"text": block})
            yield {"type": "attached", "paths": labels}
        linked, problems = images.from_message(text, root)
        shown = [(b, "pasted") for b in (pasted or [])] + linked
        for problem in problems:
            yield {"type": "notice", "message": f"Couldn't attach image {problem}"}
        if shown:
            content += [b for b, _ in shown][:images.MAX_PER_MESSAGE]
            yield {"type": "attached_images", "images": [{"url": images.save(self.cfg.home, b), "source": src}
                                                         for b, src in shown[:images.MAX_PER_MESSAGE]]}
        started = self._spec_for_message(session_id, root, text)
        if started:
            yield started
        guide = self._message_steering(session_id, root, text)
        if guide:
            content.append({"text": guide[0]})
            yield {"type": "steering", "names": guide[1]}
        turn_context = self._turn_context(self.store.get_session(session_id), root)
        if turn_context:
            content.append({"text": turn_context})
        route = self._start_turn(session_id, text)
        if route:
            yield route
        last = self.store.last_message(session_id)
        if last and last[1]["role"] == "user":
            # A stop or error left the conversation ending on our side; Bedrock needs alternating roles.
            self.store.replace_content(last[0], last[1]["content"] + content)
            mid = last[0]
        else:
            mid = self.store.add_message(session_id, "user", content)
        yield {"type": "turn", "mid": mid}
        yield from self._loop(session_id)

    # -- specs ----------------------------------------------------------------------------------

    def _spec_for_message(self, session_id: str, root: Path | None, text: str) -> dict | None:
        """In Spec mode with no active spec, the message describes a new one: create it."""
        sess = self.store.get_session(session_id)
        state = dict(sess.context_state or {})
        if sess.mode != "spec" or root is None or (state.get("spec") and specs.get(root, state["spec"])):
            return None
        kind = "bugfix" if re.search(r"\b(bug|broken|fails?|failing|error|crash|regression|wrong)\b", text, re.I) \
            else "feature"
        base_name, n = specs.slug(text), 1
        name = base_name
        while specs.get(root, name):
            n += 1
            name = f"{base_name}-{n}"
        spec = specs.create(root, name, kind)
        state["spec"] = spec.name
        self.store.update_session(session_id, context_state=state)
        return {"type": "spec", "name": spec.name, "created": True, "kind": kind}

    def _spec_blocks(self, sess: Session, root: Path | None, tu: dict) -> str | None:
        """Before the task list is approved, a spec session plans; it doesn't edit code."""
        if sess.mode != "spec" or tu["name"] != "propose_edit" or root is None:
            return None
        name = (self.store.get_session(sess.id).context_state or {}).get("spec")
        spec = specs.get(root, name) if name else None
        if spec and spec.phase != "implement":
            return (f"Spec '{spec.name}' is in the {spec.phase} phase: code changes wait until the user approves "
                    "the task list. Write the spec with write_spec.")
        return None

    # -- steering: always-on docs live in the system prompt; these load the rest when they apply --------

    def _steering_loaded(self, session_id: str) -> set[str]:
        return set((self.store.get_session(session_id).context_state or {}).get("steering_loaded", []))

    def _mark_steering(self, session_id: str, docs: list) -> None:
        state = dict(self.store.get_session(session_id).context_state or {})
        state["steering_loaded"] = sorted(set(state.get("steering_loaded", [])) | {d.label for d in docs})
        self.store.update_session(session_id, context_state=state)

    def _message_steering(self, session_id: str, root: Path | None, text: str) -> tuple[str, list[str]] | None:
        """Docs the user asked for with #name, and fileMatch docs for files they @-referenced."""
        asked = steering.requested(text, root, self.cfg.home)
        rels = [m["rel"] for m in mentions.find_mentions(root, text) if m["path"].is_file()]
        skip = self._steering_loaded(session_id) | {d.label for d in asked}
        matched = steering.for_files(rels, root, self.cfg.home, skip) if rels else []
        if not asked and not matched:
            return None
        self._mark_steering(session_id, asked + matched)
        parts = [steering.render(d, root, "requested by the user") for d in asked]
        parts += [steering.render(d, root, "applies to " + ", ".join(d.patterns)) for d in matched]
        return "\n\n".join(parts), [d.name for d in asked + matched]

    def _file_steering(self, ctx: ToolContext, tu: dict) -> list:
        """fileMatch docs for a file the model just read or edited (each loads once per session)."""
        if tu["name"] not in ("read_file", "propose_edit") or ctx.root is None:
            return []
        try:
            path = ctx.resolve(str(tu["input"].get("path", "")), must_exist=False)
        except ToolError:
            return []
        docs = steering.for_files([ctx.rel(path)], ctx.root, self.cfg.home, self._steering_loaded(ctx.session_id))
        if docs:
            self._mark_steering(ctx.session_id, docs)
        return docs

    def _turn_context(self, sess: Session, root: Path | None) -> str:
        """Per-turn facts that change (mode, git state, applied proposals), sent in the user message.

        Keeping them out of the system prompt keeps every earlier request a byte-identical prefix of the next
        one: prompt caching stays warm, and newer Claude models keep their earlier reasoning valid.
        """
        state = dict(sess.context_state or {})
        lines = []
        mode = modes.get(sess.mode, root, self.cfg.home)
        if state.get("mode") != mode.name:
            lines.append(f"Mode is now {mode.label}.\n" + modes.system_text(mode, root, self.cfg.home))
            state["mode"] = mode.name
        else:
            lines.append(f"Mode: {mode.label} (unchanged).")
        git = _git_summary(root)
        if git and git != state.get("git"):
            lines.append("Git:\n" + git)
            state["git"] = git
        auto = bool(state.get("auto_apply")) and not self.cfg.auto_apply_edits
        if auto != bool(state.get("auto_apply_told")):
            lines.append("Auto-apply is now ON for this session: propose_edit writes the change immediately (the user "
                         "can undo it), so verify each change with tests right after making it." if auto else
                         "Auto-apply is now OFF: proposed edits wait for the user to apply them.")
            state["auto_apply_told"] = auto
        spec_name = state.get("spec") if mode.name == "spec" else None
        spec = specs.get(root, spec_name) if spec_name and root else None
        if spec:
            lines.append(specs.turn_text(root, spec))
        outcomes = self.store.take_unreported_outcomes(sess.id)
        for p in outcomes:
            note = {"outdated": f"Proposal #{p.id} ({p.path}) is outdated: the file changed, so it can no longer be "
                                "applied. Propose it again against the current file if it's still needed.",
                    "superseded": f"Proposal #{p.id} ({p.path}) was replaced by your newer proposal for the same "
                                  "lines."}.get(p.status, f"Proposal #{p.id} ({p.path}) was {p.status} by the user.")
            if p.status == "applied" and p.check_text:
                note += f" Automatic checks on the file found:\n{p.check_text}"
            lines.append(note)
        self.store.update_session(sess.id, context_state=state)
        return "<turn_context>\n" + "\n\n".join(lines) + "\n</turn_context>" if lines else ""

    def tier_model(self, tier: str) -> str:
        """The tier's configured model, or the best enabled fallback if discovery found it unavailable."""
        return models.resolve_tiers(self.cfg, models.cached(self.cfg))["main" if tier == "auto" else tier]["model"]

    def auto_model(self, tier: str) -> str:
        """Auto uses the newest model of each class this account can use: Haiku (fast), Sonnet (main, the
        default), Opus (hard). Without discovery results (or for non-Claude providers) it uses the tier's model."""
        return models.best_in_family(models.cached(self.cfg), models.AUTO_FAMILIES[tier]) or self.tier_model(tier)

    def _model_for(self, sess: Session) -> str:
        """The model for this session's current turn: a pinned model, Auto's pick, or the mode's/session's tier."""
        if sess.model:
            return sess.model
        root = Path(sess.repo).expanduser().resolve() if sess.repo else None
        mode = modes.get(sess.mode, root, self.cfg.home)
        if sess.tier == "auto":
            route = (sess.context_state or {}).get("route") or {}
            return self.auto_model(route.get("tier") or mode.tier or "main")
        return self.tier_model(mode.tier or sess.tier)

    # -- Auto routing and turn bookkeeping ------------------------------------------------------

    def _start_turn(self, session_id: str, text: str) -> dict | None:
        """Reset per-turn counters; with Auto, choose this turn's tier. Returns the route event, if any."""
        sess = self.store.get_session(session_id)
        state = dict(sess.context_state or {})
        state["turn"] = {"failures": 0, "advised": False, "hit_limit": False}
        event = None
        if sess.tier == "auto" and not sess.model:
            root = Path(sess.repo).expanduser().resolve() if sess.repo else None
            mode = modes.get(sess.mode, root, self.cfg.home)
            pick = router.choose(mode.name, text, state.get("last_turn"))
            if mode.tier and pick.reason == "routine work":  # a custom mode's own tier beats the default rule
                pick = router.Route(mode.tier, f"{mode.label} mode prefers {mode.tier}")
            model = self.auto_model(pick.tier)
            state["route"] = {"tier": pick.tier, "reason": pick.reason, "model": model}
            event = {"type": "route", "tier": pick.tier, "model": model, "reason": pick.reason}
        model = self._model_for(Session(**{**sess.__dict__, "context_state": state}))
        if state.get("last_model") and state["last_model"] != model:
            # Another model can't validate this one's signed reasoning; drop it once at the switch.
            self.store.update_session(session_id, context_state=state)
            self._strip_reasoning(session_id)
            state = dict(self.store.get_session(session_id).context_state or {})
        state["last_model"] = model
        self.store.update_session(session_id, context_state=state)
        return event

    def _end_turn(self, session_id: str) -> None:
        state = dict(self.store.get_session(session_id).context_state or {})
        state["last_turn"] = state.pop("turn", {})
        self.store.update_session(session_id, context_state=state)

    def _turn_flag(self, session_id: str, **changes) -> dict:
        state = dict(self.store.get_session(session_id).context_state or {})
        turn = {**{"failures": 0, "advised": False, "hit_limit": False}, **state.get("turn", {})}
        for k, v in changes.items():
            turn[k] = turn.get(k, 0) + v if k == "failures" else v
        state["turn"] = turn
        self.store.update_session(session_id, context_state=state)
        return turn

    def _after_result(self, session_id: str, tu: dict, output: str, is_error: bool) -> Generator[dict, None, str]:
        """Count failing runs; on the second one in a turn under Auto, consult the hard model once."""
        if not router.failed_run(tu["name"], output, is_error):
            return output
        turn = self._turn_flag(session_id, failures=1)
        sess = self.store.get_session(session_id)
        if sess.tier != "auto" or sess.model or turn["failures"] < 2 or turn["advised"]:
            return output
        advisor = self.auto_model("hard")
        if advisor == self._model_for(sess):
            return output
        self._turn_flag(session_id, advised=True)
        yield {"type": "notice", "message": f"Auto: runs keep failing, so asking {advisor} for a second opinion…"}
        transcript = render_transcript(self.store.live_messages(session_id)[-24:], limit=60_000)
        prompt = (f"{transcript}\n\nThe latest {tu['name']} result:\n{output[-6000:]}\n\n"
                  "Give your advice now.")
        try:
            advice = self.llm.complete(advisor, prompts.ADVISOR, prompt, max_tokens=1500)
        except BedrockError as exc:
            yield {"type": "notice", "message": f"Second opinion unavailable: {exc}"}
            return output
        yield {"type": "advisor", "model": advisor, "text": advice}
        return (f"{output}\n\n<advisor model=\"{advisor}\">\n{advice}\n</advisor>\n"
                "Consider this advice before your next step.")

    def context_usage(self, session_id: str) -> dict:
        """Estimated prompt tokens against the model's budget (window minus reply reserve)."""
        sess = self.store.get_session(session_id)
        system = (sess.context_state or {}).get("system") or []
        return self.ctxm.usage_view(session_id, self._model_for(sess), system,
                                    [t.spec() for t in self.tools.values()])

    def compact(self, session_id: str, focus: str = "") -> Iterator[dict]:
        """Manual compaction (/compact [focus] or the Compact button)."""
        changed = yield from self.ctxm.compact_now(session_id, focus)
        if changed:
            self._strip_reasoning(session_id)
            yield {"type": "notice", "message": "Compacted. Earlier conversation is summarised in Memory; the "
                                                "assistant keeps the summary and working state."}
        yield self.context_usage(session_id)
        yield {"type": "done"}

    def handoff(self, session_id: str) -> str:
        """Start a fresh session on the same folder, seeded with this one's summary (like Cline's new_task)."""
        for _ in self.ctxm.compact_now(session_id):
            pass
        old = self.store.get_session(session_id)
        new = self.store.create_session(old.repo, old.tier, auto_approve=old.auto_approve)
        self.store.update_session(new.id, summary=old.summary, mode=old.mode,
                                  title=f"{(old.title or 'Session')[:60]} (continued)")
        return new.id

    def resume(self, session_id: str, approve: bool, remember: bool = False, feedback: str = "") -> Iterator[dict]:
        sess = self.store.get_session(session_id)
        self._cancelled.discard(session_id)
        pending = sess.pending
        if not pending:
            yield {"type": "error", "message": "Nothing is waiting for approval."}
            return
        if approve and remember:
            self.allow(session_id, [r for r in (allow_rule(tu) for tu in pending["awaiting"]) if r])
        ctx = self._ctx(sess)
        results = list(pending["results"])
        for tu in pending["awaiting"]:
            if approve:
                yield {"type": "tool_running", "id": tu["toolUseId"], "name": tu["name"]}
                output, is_error, took = yield from self._exec(ctx, tu)
            else:
                output, is_error, took = ("The user declined this tool call" + (" and wrote the message below instead."
                                                                             if feedback else "."), True, 0.0)
            yield from self._drain(ctx)
            yield self._result_event(tu, output, is_error, took)
            output = yield from self._after_result(session_id, tu, output, is_error)
            results.append(_tool_result(tu["toolUseId"], output, is_error))
        self.store.update_session(session_id, pending=None)
        content = _order_results(pending["order"], results) + ([{"text": feedback}] if feedback else [])
        self.store.add_message(session_id, "user", content)
        yield from self._loop(session_id)
        yield from self._drain_queue_turns(session_id)

    # -- "always allow" rules for this session ---------------------------------------------------

    def allowed(self, session_id: str, tu: dict) -> bool:
        rules = (self.store.get_session(session_id).context_state or {}).get("allow", [])
        return any(rule_matches(r, tu) for r in rules)

    def allow(self, session_id: str, rules: list[dict]) -> None:
        state = dict(self.store.get_session(session_id).context_state or {})
        current = state.get("allow", [])
        state["allow"] = current + [r for r in rules if r not in current]
        self.store.update_session(session_id, context_state=state)

    def approval_view(self, awaiting: list[dict], root: Path | None) -> list[dict]:
        return [{"id": tu["toolUseId"], "name": tu["name"], "input": tu["input"], "command": self.describe(tu, root),
                 "allow": allow_rule(tu)} for tu in awaiting]

    def describe(self, tu: dict, root: Path | None) -> str:
        """Human-readable form of an approval-gated call."""
        inp = tu["input"]
        if tu["name"] == "run_command":
            return inp.get("command", "")
        if tu["name"] == "open_workspace":
            return f"open workspace {inp.get('path', '')}"
        if tu["name"] == "run_tests":
            cmd = detect_test_cmd(root, self.cfg) or "(no test command detected)"
            return f"{cmd} {inp.get('args', '')}".strip()
        if tu["name"] == "github":
            return f"gh {str(inp.get('args', '')).removeprefix('gh ')}"
        if tu["name"] == "web_fetch":
            return f"fetch {inp.get('url', '')}"
        if tu["name"] == "run_checks":
            names = ", ".join(c.name for c in checks.detect(root)) if root else ""
            return f"run checks ({inp.get('kind', 'all')}): {names or 'none detected'}"
        return f"{tu['name']} {json.dumps(inp)}"

    # -- internals ------------------------------------------------------------------------------

    def _ctx(self, sess: Session) -> ToolContext:
        root = Path(sess.repo).expanduser().resolve() if sess.repo else None
        return ToolContext(root=root, cfg=self.cfg, store=self.store, session_id=sess.id,
                           logs_client_factory=self._logs_factory,
                           auto_apply=bool((sess.context_state or {}).get("auto_apply")))

    def _system(self, sess: Session, ctx: ToolContext) -> list[dict]:
        root = ctx.root
        top: list[str] = []
        if root is not None:
            try:
                top = sorted(p.name + ("/" if p.is_dir() else "") for p in root.iterdir() if p.name not in SKIP_DIRS)
            except OSError:
                pass
        return prompts.build_system(
            root, detect_test_cmd(root, self.cfg), self.cfg.eval_cmd, trace_roots(ctx) if root else [],
            self.cfg.log_groups, self.store.read_notes(str(root)) if root else "", sess.summary, top,
            skills.discover(root, self.cfg.home), steering.always_text(root, self.cfg.home),
            steering_auto=steering.auto_listing(root, self.cfg.home),
            repo_map=repomap.build(root) if root else "",
            checks=[c.name for c in checks.detect(root)] if root else [], auto_apply=self.cfg.auto_apply_edits)

    def _session_system(self, sess: Session, ctx: ToolContext) -> list[dict]:
        """The system prompt, frozen per session. It is rebuilt only at a boundary (new workspace, or memory
        compaction), and then reasoning blocks from the old prefix are dropped once so they can't fail
        Claude's conversation check."""
        state = dict(sess.context_state or {})
        # Editing a steering doc changes the key, so new instructions apply from the next request.
        key = f"{ctx.root}|{hash(sess.summary)}|{steering.fingerprint(ctx.root, self.cfg.home)}"
        if state.get("system") and state.get("key") == key:
            return state["system"]
        system = self._system(sess, ctx)
        if state.get("system"):
            self._strip_reasoning(sess.id)
        state = dict(self.store.get_session(sess.id).context_state or {})
        state.update({"system": system, "key": key, "steering_loaded": []})  # re-load file docs when they apply
        self.store.update_session(sess.id, context_state=state)
        return system

    def _strip_reasoning(self, session_id: str) -> None:
        for mid, msg in self.store.messages(session_id):
            kept = [b for b in msg["content"] if "reasoningContent" not in b]
            if len(kept) != len(msg["content"]):
                self.store.replace_content(mid, kept or [{"text": "(reasoning omitted)"}])

    @staticmethod
    def _drain(ctx: ToolContext) -> Iterator[dict]:
        events, ctx.events = ctx.events, []
        yield from events

    def _loop(self, session_id: str) -> Iterator[dict]:
        for event in self._loop_steps(session_id):
            if event["type"] == "done":
                self._end_turn(session_id)
            yield event

    def _loop_steps(self, session_id: str) -> Iterator[dict]:
        sess = self.store.get_session(session_id)
        ctx = self._ctx(sess)
        if ctx.root is not None and not ctx.root.is_dir():
            yield {"type": "error", "message": f"Workspace path does not exist: {ctx.root}"}
            return
        mode = modes.get(sess.mode, ctx.root, self.cfg.home)
        model = self._model_for(sess)
        system = self._session_system(sess, ctx)
        specs = [t.spec() for t in self.tools.values()]
        recovered = False
        step = 0
        while step < self.cfg.max_steps:
            step += 1
            yield from self._deliver_queue(session_id)
            changed = yield from self.ctxm.ensure_room(session_id, model, system, specs)
            if changed:
                self._strip_reasoning(session_id)
                system = self._session_system(self.store.get_session(session_id), ctx)
            final = None
            partial = ""
            started = time.monotonic()
            sent = self.store.live_messages(session_id)
            try:
                for event in self.llm.stream(model, system, sent, specs):
                    if session_id in self._cancelled:
                        break
                    if event["type"] == "message":
                        final = event
                    else:
                        if event["type"] == "text":
                            partial += event["text"]
                        yield event
            except BedrockError as exc:
                if is_overflow(exc) and not recovered and not partial:
                    recovered = True
                    step -= 1
                    yield {"type": "notice", "message": "The conversation no longer fits the model's context "
                                                        "window. Compacting and retrying…"}
                    if (yield from self.ctxm.recover(session_id, model)):
                        self._strip_reasoning(session_id)
                        system = self._session_system(self.store.get_session(session_id), ctx)
                        continue
                hint = (" Use /compact, or Memory → Continue in new session." if is_overflow(exc) else "")
                yield {"type": "error", "message": str(exc) + hint}
                yield self.context_usage(session_id)
                yield {"type": "done"}
                return
            if session_id in self._cancelled:
                self.store.add_message(session_id, "assistant", [{"text": (partial + "\n\n_(stopped)_").strip()}])
                yield from self._stopped(session_id)
                return
            content = final["content"] if final else []
            if not content:
                content = [{"text": "(no response)"}]
            tool_uses = [b["toolUse"] for b in content if "toolUse" in b]
            invalid = {tu["toolUseId"]: tu.pop("_invalid_input") for tu in tool_uses if "_invalid_input" in tu}
            self.store.add_message(session_id, "assistant", content)
            usage = (final or {}).get("usage") or {}
            if usage:
                self.store.add_usage(session_id, model, usage)
                self.ctxm.record(session_id, system, specs, sent, usage)
            yield {"type": "usage", "model": model, "usage": usage, "seconds": round(time.monotonic() - started, 1)}
            stop = (final or {}).get("stop_reason")
            if not tool_uses:
                if stop == "max_tokens":
                    yield {"type": "notice", "message": "Reply hit the max token limit (CODEPILOT_MAX_TOKENS)."}
                yield self.context_usage(session_id)
                yield {"type": "done"}
                return

            root_before = ctx.root
            results, awaiting = [], []
            for tu in tool_uses:
                yield {"type": "tool_call", "id": tu["toolUseId"], "name": tu["name"], "input": tu["input"]}
                tool = self.tools.get(tu["name"])
                if session_id in self._cancelled:
                    output, is_error, took = "Cancelled: the user stopped this turn.", True, 0.0
                elif self._spec_blocks(sess, ctx.root, tu):
                    output, is_error, took = self._spec_blocks(sess, ctx.root, tu), True, 0.0
                elif tu["name"] in mode.blocked:
                    output, is_error, took = (f"{tu['name']} is disabled in {mode.label} mode. Work within the mode; "
                                              "the user can switch modes if they want this."), True, 0.0
                elif tu["toolUseId"] in invalid:
                    output, is_error, took = ("Tool input was not valid JSON (possibly truncated by the token "
                                              "limit). Retry with smaller input."), True, 0.0
                elif tool is None:
                    output, is_error, took = f"Unknown tool {tu['name']!r}.", True, 0.0
                elif tool.requires_approval(tu["input"], sess.auto_approve) and not _reopens(tu, ctx.root) \
                        and not self.allowed(session_id, tu):
                    awaiting.append(tu)
                    continue
                else:
                    output, is_error, took = yield from self._exec(ctx, tu)
                yield from self._drain(ctx)
                yield self._result_event(tu, output, is_error, took)
                output = yield from self._after_result(session_id, tu, output, is_error)
                results.append(_tool_result(tu["toolUseId"], output, is_error))
            if awaiting:
                self.store.update_session(session_id, pending={
                    "results": results, "awaiting": awaiting, "order": [tu["toolUseId"] for tu in tool_uses]})
                yield {"type": "approval_needed", "tools": self.approval_view(awaiting, ctx.root)}
                return
            self.store.add_message(session_id, "user", results)
            if session_id in self._cancelled:
                yield from self._stopped(session_id)
                return
            if ctx.root != root_before:
                system = self._session_system(self.store.get_session(session_id), ctx)
        self._turn_flag(session_id, hit_limit=True)
        yield {"type": "notice", "message": f"Stopped after {self.cfg.max_steps} steps (CODEPILOT_MAX_STEPS). "
                                            "Say 'continue' to keep going."}
        yield self.context_usage(session_id)
        yield {"type": "done"}

    def _stopped(self, session_id: str) -> Iterator[dict]:
        self._cancelled.discard(session_id)
        yield {"type": "notice", "message": "Stopped."}
        yield self.context_usage(session_id)
        yield {"type": "done"}

    def _exec(self, ctx: ToolContext, tu: dict) -> Generator[dict, None, tuple[str, bool, float]]:
        started = time.monotonic()
        if tu["name"] == "explore":
            output, is_error = yield from self._explore(ctx, tu)
        else:
            output, is_error = execute(self.tools[tu["name"]], ctx, tu["input"])
            docs = [] if is_error else self._file_steering(ctx, tu)
            if docs:
                why = "applies to " + ", ".join(sorted({p for d in docs for p in d.patterns}))
                output += "\n\n" + "\n\n".join(steering.render(d, ctx.root, why) for d in docs) + \
                    "\nFollow the steering above when working on these files."
                yield {"type": "steering", "names": [d.name for d in docs], "file": str(tu["input"].get("path", ""))}
        return output, is_error, time.monotonic() - started

    # -- explore sub-agent ----------------------------------------------------------------------

    def _explore(self, ctx: ToolContext, tu: dict) -> Generator[dict, None, tuple[str, bool]]:
        """A read-only nested loop on the fast model. Only its final report enters the main conversation."""
        task = str(tu["input"].get("task", "")).strip()
        if not task:
            return "explore needs a task", True
        if ctx.root is None:
            return "No workspace is open; call open_workspace first.", True
        tools = {n: t for n, t in self.tools.items() if t.read_only and not t.needs_approval and t.fn is not None
                 and n not in ("load_skill",)}
        specs = [t.spec() for t in tools.values()]
        model = self.tier_model("fast")
        system = [{"text": prompts.EXPLORE}, {"text": f"Workspace: {ctx.root}", "dynamic": True}]
        messages: list[dict] = [{"role": "user", "content": [{"text": task}]}]
        for step in range(EXPLORE_MAX_STEPS):
            if ctx.session_id in self._cancelled:
                return "Cancelled: the user stopped this turn.", True
            if step == EXPLORE_MAX_STEPS - 1:
                messages[-1]["content"].append({"text": "Step limit reached: write your final report now."})
            _shrink_local(messages, self.ctxm.budget(model) // 2, self.ctxm.ratio(ctx.session_id))
            final = None
            try:
                for event in self.llm.stream(model, system, messages, specs):
                    if event["type"] == "message":
                        final = event
            except BedrockError as exc:
                return f"explore failed: {exc}", True
            content = (final or {}).get("content") or [{"text": "(no response)"}]
            if final and final.get("usage"):
                self.store.add_usage(ctx.session_id, model, final["usage"])
            calls = [b["toolUse"] for b in content if "toolUse" in b]
            for c in calls:
                c.pop("_invalid_input", None)
            messages.append({"role": "assistant", "content": content})
            if not calls:
                return "".join(b["text"] for b in content if "text" in b).strip() or "(empty report)", False
            results = []
            for c in calls:
                yield {"type": "sub_tool", "parent": tu["toolUseId"], "name": c["name"],
                       "detail": arg_summary(c["input"])}
                tool = tools.get(c["name"])
                if tool and tool.requires_approval(c["input"], False):
                    out, err = "This call needs the user's approval, so explore can't make it.", True
                elif tool:
                    out, err = execute(tool, ctx, c["input"])
                else:
                    out, err = f"Tool {c['name']!r} is not available here.", True
                results.append(_tool_result(c["toolUseId"], out, err))
            messages.append({"role": "user", "content": results})
        return "explore stopped without a report", True

    def _result_event(self, tu: dict, output: str, is_error: bool, took: float) -> dict:
        shown = output if len(output) <= UI_OUTPUT_LIMIT else output[:UI_OUTPUT_LIMIT] + "\n[... truncated in UI]"
        event = {"type": "tool_result", "id": tu["toolUseId"], "name": tu["name"], "output": str(shown),
                 "is_error": is_error, "seconds": round(took, 2)}
        if getattr(output, "images", None):
            event["images"] = [images.save(self.cfg.home, b) for b in output.images]
        return event

def _shrink_local(messages: list[dict], max_tokens: int, ratio: float, keep_last: int = 2) -> None:
    """Explore sub-agent: clear older tool outputs in its private history if it outgrows half the budget."""
    if len(json.dumps(messages, default=str)) * ratio <= max_tokens:
        return
    results = [b for m in messages for b in m["content"] if "toolResult" in b]
    for b in results[:-keep_last]:
        tr = b["toolResult"]
        text = "".join(c.get("text", "") for c in tr.get("content", []))
        if len(text) > 400 and not text.startswith(CLEARED_PREFIX):
            tr["content"] = [{"text": f"{CLEARED_PREFIX} {len(text):,} chars. Re-run the tool if needed.]"}]


def _reopens(tu: dict, root: Path | None) -> bool:
    """open_workspace on the folder that's already open needs no approval (models often call it redundantly)."""
    if tu["name"] != "open_workspace" or root is None:
        return False
    try:
        return Path(str(tu["input"].get("path", ""))).expanduser().resolve() == root
    except (OSError, RuntimeError):
        return False


def _git_summary(root: Path | None) -> str:
    """Branch, short status and recent commits: cheap orientation for reviews and debugging."""
    if root is None or not (root / ".git").exists():
        return ""
    import subprocess

    def run(*args: str) -> str:
        try:
            proc = subprocess.run(["git", "--no-pager", "-C", str(root), *args], capture_output=True, text=True,
                                  timeout=10, errors="replace", check=False)
        except (OSError, subprocess.SubprocessError):
            return ""
        return proc.stdout.strip() if proc.returncode == 0 else ""

    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    status = run("status", "--short").splitlines()
    log = run("log", "--oneline", "-5")
    parts = [f"branch {branch or '?'}"]
    if status:
        parts.append(f"uncommitted ({len(status)}): " + ", ".join(line[3:] for line in status[:25])
                     + (" ..." if len(status) > 25 else ""))
    else:
        parts.append("working tree clean")
    if log:
        parts.append("recent commits:\n" + log)
    return "\n".join(parts)


def render_transcript(messages: list[dict], limit: int = 120_000) -> str:
    lines = []
    for m in messages:
        for b in m["content"]:
            if "text" in b:
                lines.append(f"{m['role'].upper()}: {b['text']}")
            elif "toolUse" in b:
                lines.append(f"TOOL CALL {b['toolUse']['name']}: {json.dumps(b['toolUse']['input'])[:400]}")
            elif "toolResult" in b:
                body = " ".join(c.get("text", "") for c in b["toolResult"].get("content", []))
                lines.append(f"TOOL RESULT: {body[:800]}")
            elif "image" in b:
                lines.append(f"{m['role'].upper()}: [image]")
    text = "\n".join(lines)
    return text if len(text) <= limit else text[-limit:]


def _tool_result(tool_use_id: str, output: str, is_error: bool) -> dict:
    content = [{"text": str(output) or "(empty)"}] + list(getattr(output, "images", None) or [])
    return {"toolResult": {"toolUseId": tool_use_id, "content": content,
                           "status": "error" if is_error else "success"}}


QUEUED_PREFIX = "(Sent while you were working) "
SHELL_CHAINING = re.compile(r"[;&|`$<>\n\\]")
# Programs whose next word says what runs ("npm test" vs "npm publish"), so a rule keeps that word too.
RUNNERS = {"npm", "npx", "pnpm", "yarn", "bun", "uv", "uvx", "poetry", "pipenv", "make", "go", "cargo", "bundle",
           "dotnet", "mvn", "gradle", "./gradlew", "docker", "terraform", "kubectl", "aws", "node", "deno"}


def allow_rule(tu: dict) -> dict | None:
    """The "always allow in this session" rule offered for an approval: a command prefix, never a whole shell.
    Commands that chain or redirect (;, &&, |, $(), >) get no rule: a prefix can't make them safe."""
    import shlex

    if tu["name"] == "run_command":
        cmd = str(tu["input"].get("command", "")).strip()
        if not cmd or SHELL_CHAINING.search(cmd):
            return None
        try:
            words = shlex.split(cmd)
        except ValueError:
            return None
        if words[0] in ("sudo", "rm", "git", "chmod", "chown", "dd", "mv", "curl", "wget", "ssh", "scp"):
            return None  # destructive or outward-facing: always ask
        n = 3 if len(words) > 2 and words[0].startswith("python") and words[1] == "-m" else \
            2 if words[0] in RUNNERS and len(words) > 1 else 1
        return {"tool": "run_command", "prefix": " ".join(words[:n])}
    if tu["name"] == "github":
        args = str(tu["input"].get("args", "")).removeprefix("gh ").split()
        return {"tool": "github", "prefix": " ".join(args[:2])} if len(args) >= 2 else None
    if tu["name"] == "web_fetch":
        host = webtools.host_of(str(tu["input"].get("url", "")))
        return {"tool": "web_fetch", "prefix": host} if host else None  # exactly this host, not its subdomains
    return None


def rule_matches(rule: dict, tu: dict) -> bool:
    if rule.get("tool") != tu["name"]:
        return False
    if tu["name"] == "web_fetch":
        return bool(rule.get("prefix")) and webtools.host_of(str(tu["input"].get("url", ""))) == rule["prefix"]
    value = str(tu["input"].get("command" if tu["name"] == "run_command" else "args", "")).strip()
    value = value.removeprefix("gh ") if tu["name"] == "github" else value
    if tu["name"] == "run_command" and SHELL_CHAINING.search(value):
        return False
    prefix = rule.get("prefix", "")
    return bool(prefix) and (value == prefix or value.startswith(prefix + " "))


def _order_results(order: list[str], results: list[dict]) -> list[dict]:
    by_id = {r["toolResult"]["toolUseId"]: r for r in results}
    return [by_id[i] for i in order if i in by_id]


def history_events(store: Store, session_id: str) -> list[dict]:
    """Rebuild UI events from stored messages (including archived ones) to redraw a session."""
    home = store.home
    events: list[dict] = []
    names: dict[str, str] = {}
    live = {mid for mid, _ in store.messages(session_id)}
    for mid, m in store.messages(session_id, include_archived=True):
        # A message that starts a turn (and isn't compacted) can be edited or retried from the UI.
        starts_turn = m["role"] == "user" and bool(m["content"]) and "text" in m["content"][0] and mid in live
        for i, b in enumerate(m["content"]):
            if "text" in b and m["role"] == "user" and b["text"].startswith("<turn_context>"):
                continue
            if "text" in b and m["role"] == "user" and b["text"].startswith("<skill name="):
                events.append({"type": "skill", "name": b["text"].split('"')[1]})
            elif "text" in b and m["role"] == "user" and b["text"].startswith("<steering "):
                events.append({"type": "steering", "names": re.findall(r'<steering name="([^"]+)"', b["text"])})
            elif "text" in b and m["role"] == "user" and b["text"].startswith(mentions.ATTACH_OPEN):
                events.append({"type": "attached", "paths": mentions.attached_labels(b["text"])})
            elif "text" in b and m["role"] == "user":
                queued = b["text"].startswith(QUEUED_PREFIX)
                event = {"type": "user", "text": b["text"].removeprefix(QUEUED_PREFIX)}
                if starts_turn and i == 0:
                    event["mid"] = mid
                elif queued:
                    event["queued"] = True
                events.append(event)
            elif "text" in b:
                events.append({"type": "assistant", "text": b["text"]})
            elif "toolUse" in b:
                tu = b["toolUse"]
                names[tu["toolUseId"]] = tu["name"]
                events.append({"type": "tool_call", "id": tu["toolUseId"], "name": tu["name"], "input": tu["input"]})
                if tu["name"] == "update_plan" and isinstance(tu["input"].get("items"), list):
                    events.append({"type": "plan", "items": tu["input"]["items"]})
            elif "image" in b and m["role"] == "user":
                url = images.save(home, b)
                if events and events[-1]["type"] == "attached_images":
                    events[-1]["images"].append({"url": url, "source": ""})
                else:
                    events.append({"type": "attached_images", "images": [{"url": url, "source": ""}]})
            elif "toolResult" in b:
                tr = b["toolResult"]
                out = " ".join(c.get("text", "") for c in tr.get("content", []))
                tu = {"toolUseId": tr["toolUseId"], "name": names.get(tr["toolUseId"], "")}
                shown = out if len(out) <= UI_OUTPUT_LIMIT else out[:UI_OUTPUT_LIMIT] + "\n[... truncated in UI]"
                event = {"type": "tool_result", "id": tu["toolUseId"], "name": tu["name"], "output": shown,
                         "is_error": tr.get("status") == "error", "seconds": 0.0}
                pics = [images.save(home, c) for c in tr.get("content", []) if "image" in c]
                if pics:
                    event["images"] = pics
                events.append(event)
                ref = re.match(r"(?:Proposed|Applied) change #(\d+)", out) if tu["name"] == "propose_edit" else None
                if ref:  # redraw the change where it was proposed, with its current status
                    events.append({"type": "proposal_ref", "id": int(ref.group(1))})
    return events
