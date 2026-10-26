"""Local web app: JSON API + NDJSON streaming for the chat, and the single-page UI."""

from __future__ import annotations

import base64
import binascii
import collections
import contextlib
import inspect
import json
import logging
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Iterator
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.websockets import WebSocket
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from . import checks, diagnostics, github, images, mentions, models, modes, skills, specs, steering, traces, version
from .agent import Agent, history_events
from .config import TIER_CHOICES, TIERS, Config
from .store import Store
from .tools import (
    SKIP_DIRS,
    retire_stale_proposals,
    ToolContext,
    ToolError,
    _locate_trace,
    _run_command,
    _trace_files,
    apply_proposal,
    detect_test_cmd,
    proposal_view,
    revert_proposal,
    search_code,
    trace_roots,
    unified_diff,
)

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
MAX_VIEW_BYTES = 2_000_000


def create_app(cfg: Config, store: Store | None = None, agent: Agent | None = None) -> Starlette:
    store = store or Store(cfg.home)
    agent = agent or Agent(cfg, store)
    busy: set[str] = set()
    busy_lock = threading.Lock()
    term_token = secrets.token_urlsafe(32)  # new every launch; embedded in the page, required by terminal routes
    from .terminal import TerminalManager

    terminals = TerminalManager()
    diagnostics.problems()  # start keeping recent warnings and errors for problem reports

    def err(message: str, status: int = 400) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    def ctx_for(sid: str) -> ToolContext:
        sess = store.get_session(sid)
        root = Path(sess.repo).expanduser().resolve() if sess.repo else None
        if root is None:
            raise ToolError("No workspace open in this session yet.")
        return ToolContext(root=root, cfg=cfg, store=store, session_id=sid)

    # A turn runs on its own thread, so closing or reloading the page doesn't stop it. Its events are kept
    # until it ends; the page that started it reads them from the start, and a reloaded page from where it is.
    runs: dict[str, dict] = {}  # sid -> {"events": [bytes], "done": bool}
    runs_cond = threading.Condition()

    def publish(run: dict, event: dict) -> None:
        with runs_cond:
            run["events"].append((json.dumps(event, default=str) + "\n").encode())
            runs_cond.notify_all()

    def run_turn(sid: str, run: dict, events: Iterator[dict]) -> None:
        current, produced = events, True
        try:
            while True:
                for event in current:
                    produced = True
                    publish(run, event)
                # A message queued as the turn was ending must not be lost: run it before letting go.
                with busy_lock:
                    if not produced or not agent.queued(sid) or not store.has_session(sid) \
                            or store.get_session(sid).pending:
                        busy.discard(sid)
                        break
                current, produced = agent.drain(sid), False
        except Exception as exc:  # surface unexpected failures in the chat instead of a dead stream
            log.error("agent failure:\n%s", traceback.format_exc())
            publish(run, {"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            publish(run, {"type": "done"})
        finally:
            with busy_lock:
                busy.discard(sid)
            with runs_cond:
                run["done"] = True
                if runs.get(sid) is run:
                    runs.pop(sid)
                runs_cond.notify_all()

    def follow_body(run: dict, start: int) -> Iterator[bytes]:
        i = start
        while True:
            with runs_cond:
                if i >= len(run["events"]) and not run["done"]:
                    runs_cond.wait(timeout=15)
                new, done = run["events"][i:], run["done"]
            i += len(new)
            yield from new
            if done and i >= len(run["events"]):
                return
            if not new:
                yield b"\n"  # keep-alive (the page skips blank lines)

    def ndjson(body: Iterator[bytes]) -> Response:
        return StreamingResponse(body, media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def stream(sid: str, events: Iterator[dict]) -> Response:
        with busy_lock:
            if sid in busy:
                return err("This session is already working; wait for it to finish.", 409)
            busy.add(sid)
        run = {"events": [], "done": False}
        with runs_cond:
            runs[sid] = run
        threading.Thread(target=run_turn, args=(sid, run, events), name=f"turn-{sid[:8]}", daemon=True).start()
        return ndjson(follow_body(run, 0))

    async def index(request: Request) -> Response:
        html = (STATIC / "index.html").read_text().replace("__CODEPILOT_TOKEN__", term_token if cfg.terminal else "")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    def term_dir(cwd: str | None, sid: str | None) -> Path:
        """An explicit folder, else the session's workspace, else home."""
        if cwd:
            path = Path(cwd).expanduser()
            if not path.is_dir():
                raise ValueError(f"Not a folder: {cwd}")
            return path.resolve()
        if sid:
            with contextlib.suppress(KeyError):
                repo = store.get_session(sid).repo
                if repo and Path(repo).is_dir():
                    return Path(repo)
        return Path.home()

    def term_allowed(headers: dict, token: str) -> bool:
        origin = headers.get("origin")
        same_origin = origin is None or origin.split("://", 1)[-1] == headers.get("host", "")
        return bool(cfg.terminal) and secrets.compare_digest(token, term_token) and same_origin

    async def terminal_ws(ws: WebSocket) -> None:
        from . import terminal

        headers = {k.decode().lower(): v.decode() for k, v in ws.scope.get("headers", [])}
        if "origin" not in headers or not term_allowed(headers, ws.query_params.get("token", "")):
            await ws.close(code=1008)  # policy violation: wrong token, wrong origin, or terminal disabled
            return
        tid = ws.query_params.get("id")
        ephemeral = not tid  # older clients: a fresh shell for this connection only
        try:
            term = terminals.get(tid) if tid else terminals.create(term_dir(None, ws.query_params.get("sid")))
        except terminal.TerminalLimit:
            term = None
        await ws.accept()
        if term is None:
            await ws.close(code=terminal.UNKNOWN)
            return
        try:
            await terminal.attach(ws, term)
        finally:
            if ephemeral:
                await run_in_threadpool(terminals.kill, term.id)

    async def terminals_view(request: Request) -> Response:
        from .terminal import TerminalLimit

        headers = {k.lower(): v for k, v in request.headers.items()}
        if not term_allowed(headers, request.headers.get("x-codepilot-terminal", "")):
            return err("Terminal access refused (disabled, or the page is from an earlier server; reload it).", 403)
        tid = request.path_params.get("tid")
        if tid is None and request.method == "POST":
            data = await request.json()
            try:
                term = terminals.create(term_dir(data.get("cwd"), data.get("sid")), str(data.get("name") or "")[:60])
            except ValueError as exc:
                return err(str(exc))
            except TerminalLimit as exc:
                return err(str(exc), 429)
            return JSONResponse(term.info(), status_code=201)
        if tid is None:
            return JSONResponse({"terminals": [t.info() for t in terminals.list()]})
        term = terminals.get(tid)
        if term is None:
            return err("No such terminal", 404)
        if request.method == "DELETE":
            await run_in_threadpool(terminals.kill, tid)
            return JSONResponse({"ok": True})
        if request.method == "PATCH":
            name = str((await request.json()).get("name") or "").strip()[:60]
            if name:
                term.name = name
        return JSONResponse(term.info())

    async def report_view(request: Request) -> Response:
        """A diagnostics report (to download) and a short redacted summary for a GitHub issue."""
        data = await request.json()
        report = await run_in_threadpool(build_report, data)
        title = str(data.get("title") or "").strip() or "Problem report"
        body = diagnostics.issue_markdown(report, str(data.get("description") or ""), title)
        return JSONResponse({"report": report, "issue_title": title, "issue_body": body,
                             "issue_url": diagnostics.issue_url(title, body),
                             "filename": time.strftime("codepilot-report-%Y%m%d-%H%M%S.json")})

    def build_report(data: dict) -> dict:
        sid = str(data.get("sid") or "")
        report: dict = {
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "environment": diagnostics.environment(version.STARTED, version.fingerprint() != version.STARTED),
            "settings": diagnostics.safe_settings(cfg),
            "models": {"tiers": models.resolve_tiers(cfg, models.cached(cfg)),
                       "on_account": [m["id"] for m in (models.cached(cfg) or {}).get("models", []) if m["available"]]},
            "terminals": len(terminals.list()),
            "server_problems": list(diagnostics.problems().records),
            "server_log": diagnostics.log_tail(cfg.home / "server.log"),
            "client": data.get("client") or {},
        }
        try:
            sess = store.get_session(sid) if sid else None
        except KeyError:
            sess = None
        if sess is not None:
            props = store.list_proposals(sid)
            usage = agent.context_usage(sid)
            state = sess.context_state or {}
            report["session"] = {
                "id": sid, "mode": sess.mode, "tier": sess.tier, "model": sess.model, "has_folder": bool(sess.repo),
                "auto_approve": sess.auto_approve, "auto_apply": bool(state.get("auto_apply")),
                "messages": len(store.messages(sid)), "archived": len(store.messages(sid, include_archived=True))
                - len(store.messages(sid)), "pending_approval": bool(sess.pending), "spec": state.get("spec"),
                "allow_rules": state.get("allow", []), "route": state.get("route"), "last_turn": state.get("last_turn"),
                "proposals": dict(collections.Counter(p.status for p in props)),
                "proposal_list": [{"id": p.id, "path": p.path, "status": p.status} for p in props],
                "context": {**{k: usage.get(k) for k in ("tokens", "budget", "window")},
                            "percent": round(100 * (usage.get("tokens") or 0) / max(1, usage.get("budget") or 1))},
            }
            if data.get("include_transcript"):
                events = history_events(store, sid)
                for ev in events:
                    for key in ("text", "output"):
                        if isinstance(ev.get(key), str) and len(ev[key]) > 2000:
                            ev[key] = ev[key][:2000] + " [...]"
                report["events"] = events
        secrets_ = tuple(os.environ.get(k, "") for k in (
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_ACCESS_KEY_ID",
            "BRAVE_API_KEY", "CODEPILOT_BRAVE_API_KEY", "CONTEXT7_API_KEY", "GH_TOKEN", "GITHUB_TOKEN")) + (term_token,)
        return diagnostics.redact_obj(report, secrets_)

    async def restart_view(request: Request) -> Response:
        """Restart this server in place (same process, same arguments) to load updated code."""
        def go() -> None:
            time.sleep(0.4)  # let the response reach the browser
            terminals.close_all()
            log.warning("restarting to load updated code")
            os.environ["PYTHONUNBUFFERED"] = "1"  # keep the background log unbuffered, as `-u` did
            os.execv(sys.executable, [sys.executable, "-m", "codepilot", *sys.argv[1:]])

        threading.Thread(target=go, daemon=True).start()
        return JSONResponse({"ok": True, "restarting": True}, status_code=202)

    async def image_view(request: Request) -> Response:
        path = images.cached(cfg.home, request.path_params["name"])
        if path is None:
            return err("No such image", 404)
        return Response(path.read_bytes(), media_type=images.MIME[path.suffix[1:]],
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})

    async def config_view(request: Request) -> Response:
        return JSONResponse({
            "provider": cfg.provider, "models": cfg.models, "tiers": list(TIERS), "default_tier": cfg.default_tier,
            "default_repo": cfg.default_repo, "test_cmd": cfg.test_cmd or "(auto-detect)", "eval_cmd": cfg.eval_cmd,
            "region": cfg.region if cfg.provider == "bedrock" else None,
            "profile": cfg.profile if cfg.provider == "bedrock" else None,
            "log_groups": cfg.log_groups, "auto_approve_default": cfg.auto_approve_tests, "terminal": cfg.terminal,
            "home": str(Path.home()),
            "version": version.STARTED, "stale": version.fingerprint() != version.STARTED,
        })

    async def sessions(request: Request) -> Response:
        if request.method == "GET":
            return JSONResponse([{**s.public(), "busy": s.id in busy} for s in store.list_sessions()])
        data = await request.json()
        repo = (data.get("repo") or "").strip()
        if repo:
            path = Path(repo).expanduser().resolve()
            if not path.is_dir():
                return err(f"Not a directory: {path}")
            repo = str(path)
        tier = data.get("tier") or cfg.default_tier
        if tier not in TIER_CHOICES:
            return err(f"tier must be one of {TIER_CHOICES}")
        sess = store.create_session(repo, tier, auto_approve=bool(data.get("auto_approve", False)))
        return JSONResponse(sess.public())

    async def follow(request: Request) -> Response:
        """Stream a running turn's events from now on (for a page opened or reloaded while it runs). 204 when
        nothing is running."""
        with runs_cond:
            run = runs.get(request.path_params["sid"])
            start = len(run["events"]) if run else 0
        return ndjson(follow_body(run, start)) if run else Response(status_code=204)

    async def session(request: Request) -> Response:
        sid = request.path_params["sid"]
        try:
            sess = store.get_session(sid)
        except KeyError:
            return err("No such session", 404)
        if request.method == "DELETE":
            store.delete_session(sid)
            return JSONResponse({"ok": True})
        if request.method == "PATCH":
            data = await request.json()
            fields = {k: data[k] for k in ("title", "tier", "auto_approve", "repo", "mode", "model") if k in data}
            if isinstance(data.get("allow"), list) or "auto_apply" in data:
                state = dict(sess.context_state or {})
                if isinstance(data.get("allow"), list):  # replace "always allow" rules (only removing is possible)
                    state["allow"] = [r for r in state.get("allow", []) if r in data["allow"]]
                if "auto_apply" in data:
                    state["auto_apply"] = bool(data["auto_apply"])
                store.update_session(sid, context_state=state)
            if "model" in fields:
                fields["model"] = str(fields["model"] or "").strip()[:200]
            if "mode" in fields:
                root_ = Path(sess.repo).expanduser().resolve() if sess.repo else None
                known = {m.name for m in modes.all_modes(root_, cfg.home)} | set(modes.ALIASES)
                if fields["mode"] not in known:
                    return err(f"unknown mode; choose one of {sorted(known)}")
            if "tier" in fields and fields["tier"] not in TIER_CHOICES:
                return err(f"tier must be one of {TIER_CHOICES}")
            if "repo" in fields:
                path = Path(str(fields["repo"])).expanduser().resolve()
                if not path.is_dir():
                    return err(f"Not a directory: {path}")
                fields["repo"] = str(path)
            if fields:
                store.update_session(sid, **fields)
            sess = store.get_session(sid)
        root = Path(sess.repo).expanduser().resolve() if sess.repo else None
        if root is not None and root.is_dir():
            await run_in_threadpool(retire_stale_proposals, store, sid, root)
        return JSONResponse({
            "session": sess.public(),
            "busy": sid in busy,
            "summary": sess.summary,
            "events": history_events(store, sid),
            "pending": sess.pending and agent.approval_view(sess.pending["awaiting"], root),
            "allow": (sess.context_state or {}).get("allow", []),
            "auto_apply": bool((sess.context_state or {}).get("auto_apply")) or cfg.auto_apply_edits,
            "spec": (sess.context_state or {}).get("spec"),
            "proposals": [_proposal_json(p, root) for p in store.list_proposals(sid)],
            "usage": store.usage(sid),
            "context": agent.context_usage(sid),
        })

    async def chat(request: Request) -> Response:
        sid = request.path_params["sid"]
        data = await request.json()
        text = (data.get("message") or "").strip()
        pasted = []
        for i, item in enumerate((data.get("images") or [])[:images.MAX_PER_MESSAGE]):
            try:
                pasted.append(images.block(base64.b64decode(str(item.get("data") or ""), validate=True)))
            except (binascii.Error, ValueError) as exc:
                return err(f"Image {i + 1}: {exc}")
        if pasted and not text:
            text = "(see the attached image)" if len(pasted) == 1 else "(see the attached images)"
        if not text:
            return err("Empty message")
        tier = data.get("tier")
        if tier and tier not in TIER_CHOICES:
            return err(f"tier must be one of {TIER_CHOICES}")
        try:
            store.get_session(sid)
        except KeyError:
            return err("No such session", 404)
        return stream(sid, agent.chat(sid, text, tier, pasted))

    gh_status: dict = {}

    async def models_view(request: Request) -> Response:
        """Models this account can use (probed/listed, cached 12h) and each tier's effective model."""
        refresh = request.query_params.get("refresh") == "1"
        data = await run_in_threadpool(models.discover, cfg, refresh)
        return JSONResponse(data)

    async def github_view(request: Request) -> Response:
        if not cfg.github:
            return JSONResponse({"available": False, "reason": "disabled (CODEPILOT_GITHUB=0)"})
        if not gh_status or request.query_params.get("refresh"):
            gh_status.clear()
            gh_status.update(await run_in_threadpool(github.status, cfg.github_host))
        return JSONResponse(gh_status)

    async def compact(request: Request) -> Response:
        sid = request.path_params["sid"]
        data = await request.json() if request.headers.get("content-length") not in (None, "0") else {}
        try:
            store.get_session(sid)
        except KeyError:
            return err("No such session", 404)
        return stream(sid, agent.compact(sid, str(data.get("focus", ""))))

    async def handoff(request: Request) -> Response:
        sid = request.path_params["sid"]
        with busy_lock:
            if sid in busy:
                return err("This session is busy; wait for it to finish.", 409)
        try:
            new_id = await run_in_threadpool(agent.handoff, sid)
        except KeyError:
            return err("No such session", 404)
        return JSONResponse(store.get_session(new_id).public())

    async def cancel(request: Request) -> Response:
        returned = agent.cancel(request.path_params["sid"])
        return JSONResponse({"ok": True, "queued": returned})

    async def queue(request: Request) -> Response:
        """Messages typed while a turn runs. 409 when nothing is running: then the UI just sends it."""
        sid = request.path_params["sid"]
        if request.method == "GET":
            return JSONResponse({"queued": agent.queued(sid)})
        if request.method == "DELETE":
            return JSONResponse({"ok": agent.dequeue(sid, request.path_params.get("qid", ""))})
        data = await request.json()
        if request.method == "PATCH":
            return JSONResponse({"ok": agent.requeue(sid, request.path_params.get("qid", ""), data.get("when"))})
        text = str(data.get("text") or "").strip()
        if not text:
            return err("Empty message")
        with busy_lock:
            if sid not in busy:
                return err("Not working right now; send it as a normal message.", 409)
            return JSONResponse(agent.enqueue(sid, text, data.get("when", "now")))

    async def rewind(request: Request) -> Response:
        sid = request.path_params["sid"]
        data = await request.json()
        text = str(data.get("message") or "").strip()
        tier = data.get("tier")
        if not text:
            return err("Empty message")
        if tier and tier not in TIER_CHOICES:
            return err(f"tier must be one of {TIER_CHOICES}")
        try:
            mid = int(data.get("mid"))
            store.get_session(sid)
        except (TypeError, ValueError):
            return err("mid must be a message id")
        except KeyError:
            return err("No such session", 404)
        return stream(sid, agent.rewind(sid, mid, text, tier))

    async def grep(request: Request) -> Response:
        ctx = ctx_for(request.path_params["sid"])
        q = request.query_params.get("q", "")
        if not q:
            return JSONResponse({"results": []})
        try:
            re.compile(q)
            pattern = q
        except re.error:
            pattern = re.escape(q)
        glob = request.query_params.get("glob", "")
        out = await run_in_threadpool(search_code, ctx, pattern, ".", glob, 300)
        results = []
        for line in out.splitlines():
            m = re.match(r"^(.+?):(\d+): (.*)$", line)
            if m:
                results.append({"path": m.group(1), "line": int(m.group(2)), "text": m.group(3)})
        return JSONResponse({"results": results, "truncated": "limit reached" in out})

    async def approve(request: Request) -> Response:
        sid = request.path_params["sid"]
        data = await request.json()
        return stream(sid, agent.resume(sid, bool(data.get("approve")), bool(data.get("remember"))))

    async def proposal_action(request: Request) -> Response:
        pid = int(request.path_params["pid"])
        action = request.path_params["action"]
        try:
            prop = store.get_proposal(pid)
        except KeyError:
            return err("No such proposal", 404)
        sess = store.get_session(prop.session_id)
        root = Path(sess.repo).expanduser().resolve()
        if action == "revert":
            try:
                revert_proposal(root, prop)
            except (ToolError, OSError) as exc:
                return err(str(exc), 409)
            store.set_proposal_status(pid, "reverted")
            return JSONResponse(_proposal_json(store.get_proposal(pid), root))
        if prop.status != "pending":
            return err(f"Proposal is already {prop.status}")
        if action == "reject":
            store.set_proposal_status(pid, "rejected")
            return JSONResponse(_proposal_json(store.get_proposal(pid), root))
        if action != "apply":
            return err("action must be apply, reject or revert", 404)
        try:
            before, after = apply_proposal(root, prop)
        except (ToolError, OSError) as exc:
            store.set_proposal_status(pid, "failed")
            return err(str(exc), 409)
        found = await run_in_threadpool(checks.quick_check, root, prop.path)
        store.record_applied(pid, before, after, found)
        retired = retire_stale_proposals(store, prop.session_id, root)  # e.g. an older version of this change
        return JSONResponse({**_proposal_json(store.get_proposal(pid), root), "checks": found,
                             "outdated": [_proposal_json(store.get_proposal(i), root) for i in retired]})

    async def usage(request: Request) -> Response:
        return JSONResponse(store.usage(request.path_params["sid"]))

    async def workspace_info(request: Request) -> Response:
        sess = store.get_session(request.path_params["sid"])
        root = Path(sess.repo).expanduser().resolve() if sess.repo else None
        return JSONResponse({"repo": sess.repo, "test_cmd": detect_test_cmd(root, cfg),
                             "modes": [m.public() for m in modes.all_modes(root, cfg.home)],
                             "checks": await run_in_threadpool(checks.summary, root) if root else [],
                             "skills": [{"name": sk.name, "description": sk.description, "path": str(sk.path),
                                         "user_only": sk.user_only}
                                        for sk in skills.discover(root, cfg.home)],
                             "instructions": skills.project_instructions(root, cfg.home)[:4000],
                             "trace_roots": [str(p) for p in await run_in_threadpool(
                                 trace_roots, ToolContext(root=root, cfg=cfg, store=store, session_id=sess.id))]
                             if root else []})

    def browse(request: Request) -> Response:  # blocking I/O: runs in a worker thread
        """Directory listing for the Open Folder dialog (folders only, names and markers, no file contents)."""
        raw = request.query_params.get("path") or str(Path.home())
        try:
            path = Path(raw).expanduser().resolve()
        except (OSError, RuntimeError):
            return err("Bad path")
        if not path.is_dir():
            return err(f"Not a folder: {path}", 404)
        show_hidden = request.query_params.get("hidden") == "1"
        dirs = []
        try:
            children = sorted(path.iterdir(), key=lambda c: c.name.lower())
        except PermissionError:
            return err(f"Permission denied: {path}", 403)
        for child in children:
            if not show_hidden and child.name.startswith("."):
                continue
            try:
                if child.is_dir():
                    dirs.append({"name": child.name, "path": str(child), "project": _project_kind(child)})
            except OSError:
                continue
        return JSONResponse({"path": str(path), "parent": str(path.parent) if path.parent != path else None,
                             "project": _project_kind(path), "dirs": dirs[:2000], "places": _places(store)})

    async def find(request: Request) -> Response:
        ctx = ctx_for(request.path_params["sid"])
        q = request.query_params.get("q", "")
        found = await run_in_threadpool(mentions.find_files, ctx.root, q, 30)
        return JSONResponse({"files": found})

    def trace_list(request: Request) -> Response:  # blocking I/O: runs in a worker thread
        ctx = ctx_for(request.path_params["sid"])
        files = []
        for f in _trace_files(ctx)[:500]:
            st = f.stat()
            try:
                shown = str(f.relative_to(ctx.root))
            except ValueError:
                shown = str(f)
            files.append({"path": shown, "size": st.st_size, "mtime": st.st_mtime})
        return JSONResponse({"roots": [str(r) for r in trace_roots(ctx)], "files": files})

    def trace_view(request: Request) -> Response:  # blocking I/O: runs in a worker thread
        ctx = ctx_for(request.path_params["sid"])
        try:
            path = _locate_trace(ctx, request.query_params.get("path", ""))
        except ToolError as exc:
            return err(str(exc), 404)
        size = path.stat().st_size
        try:
            outline = traces.outline(path)
        except (OSError, ValueError, RecursionError) as exc:
            outline = {"error": str(exc), "spans": [], "ids": {}, "records": 0, "errors": 0}
        raw = None
        if size <= MAX_VIEW_BYTES:
            try:
                raw = traces.load_records(path)
            except (OSError, ValueError):
                raw = None
        return JSONResponse({"path": str(path), "size": size, "outline": outline, "records": raw})

    def files(request: Request) -> Response:  # blocking I/O: runs in a worker thread
        ctx = ctx_for(request.path_params["sid"])
        try:
            base = ctx.resolve(request.query_params.get("path", "."))
        except ToolError as exc:
            return err(str(exc), 404)
        if base.is_file():
            if base.stat().st_size > MAX_VIEW_BYTES:
                return err("File too large to view")
            return JSONResponse({"path": ctx.rel(base), "content": base.read_text(errors="replace"),
                                 "mtime": str(base.stat().st_mtime_ns)})
        entries = []
        for p in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if p.name in SKIP_DIRS or p.name == ".DS_Store":
                continue
            entries.append({"name": p.name, "path": ctx.rel(p), "dir": p.is_dir()})
        return JSONResponse({"path": ctx.rel(base), "entries": entries})

    async def fs(request: Request) -> Response:
        """The user's own file operations from the explorer and editor (not the assistant's, which go through
        proposals). Paths are workspace-relative and must stay inside it; deletes go to a restorable trash."""
        ctx = ctx_for(request.path_params["sid"])
        data = await request.json()
        try:
            result = await run_in_threadpool(file_op, ctx, data)
            await run_in_threadpool(retire_stale_proposals, store, ctx.session_id, ctx.root)
            return JSONResponse(result)
        except FileOpError as exc:
            return err(str(exc), exc.status)
        except ToolError as exc:
            return err(str(exc), 400)
        except OSError as exc:
            return err(f"{type(exc).__name__}: {exc.strerror or exc}", 400)

    def file_op(ctx: ToolContext, data: dict) -> dict:
        op = data.get("op")
        rel = str(data.get("path") or "").strip().strip("/")
        if op == "restore":
            return restore_from_trash(ctx, str(data.get("trash_id") or ""))
        path = workspace_path(ctx, rel)
        if op in ("rename", "delete", "save") and not (path.exists() or path.is_symlink()):
            raise FileOpError(f"{rel} doesn't exist.", 404)
        if op in ("new_file", "new_folder"):
            if path.exists() or path.is_symlink():
                raise FileOpError(f"{rel} already exists.", 409)
            if op == "new_folder":
                path.mkdir(parents=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(data.get("content") or ""))
            return {"path": ctx.rel(path), "dir": op == "new_folder", "mtime": str(path.stat().st_mtime_ns)}
        if op == "rename":
            to = str(data.get("to") or "").strip().strip("/")
            dest = workspace_path(ctx, to)
            if (dest.exists() or dest.is_symlink()) and dest != path and dest.resolve() != path.resolve():
                raise FileOpError(f"{to} already exists.", 409)
            dest.parent.mkdir(parents=True, exist_ok=True)
            path.rename(dest)
            return {"path": ctx.rel(dest), "from": rel, "dir": dest.is_dir()}
        if op == "delete":
            return move_to_trash(ctx, path)
        if op == "save":
            path = ctx.resolve(rel)  # follows a symlink, but only to a target inside the workspace
            if not path.is_file():
                raise FileOpError(f"{rel} isn't a file.")
            base_mtime = data.get("base_mtime")
            if base_mtime and str(path.stat().st_mtime_ns) != str(base_mtime) and not data.get("force"):
                raise FileOpError(f"{rel} changed on disk since you opened it.", 409)
            path.write_text(str(data.get("content") or ""))
            return {"path": rel, "mtime": str(path.stat().st_mtime_ns)}
        raise FileOpError(f"Unknown operation: {op}")

    def workspace_path(ctx: ToolContext, rel: str) -> Path:
        """A path inside the workspace. The parent is resolved and checked; the last part isn't followed, so
        renaming or deleting a symlink acts on the link, never on what it points to."""
        if not rel or rel.startswith("~") or "\0" in rel or any(part in ("", ".", "..") for part in rel.split("/")):
            raise FileOpError("Enter a file or folder name inside the workspace.")
        parent = ctx.resolve(str(Path(rel).parent), must_exist=False)
        return parent / Path(rel).name

    def move_to_trash(ctx: ToolContext, path: Path) -> dict:
        trash_id = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        slot = cfg.home / "trash" / trash_id
        slot.mkdir(parents=True)
        (slot / "meta.json").write_text(json.dumps({"root": str(ctx.root), "path": ctx.rel(path),
                                                    "deleted": time.time()}))
        shutil.move(str(path), str(slot / "item"))
        return {"path": ctx.rel(path), "trash_id": trash_id, "trash": str(slot)}

    def restore_from_trash(ctx: ToolContext, trash_id: str) -> dict:
        if not re.fullmatch(r"[\w-]+", trash_id):
            raise FileOpError("Bad trash id.")
        slot = cfg.home / "trash" / trash_id
        try:
            meta = json.loads((slot / "meta.json").read_text())
        except (OSError, ValueError):
            raise FileOpError("That item is no longer in the trash.", 404) from None
        if Path(meta["root"]) != ctx.root:
            raise FileOpError("That item belongs to another workspace.", 409)
        dest = workspace_path(ctx, meta["path"])
        if dest.exists() or dest.is_symlink():
            raise FileOpError(f"{meta['path']} exists again; not overwriting it.", 409)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(slot / "item"), str(dest))
        shutil.rmtree(slot, ignore_errors=True)
        return {"path": meta["path"], "dir": dest.is_dir()}

    # -- specs ----------------------------------------------------------------------------------

    def spec_list(request: Request) -> Response:  # blocking I/O: runs in a worker thread
        ctx = ctx_for(request.path_params["sid"])
        active = (store.get_session(ctx.session_id).context_state or {}).get("spec")
        return JSONResponse({"specs": [sp.info(ctx.root) for sp in specs.discover(ctx.root)], "active": active,
                             "eval_cmd": cfg.eval_cmd})

    def set_active_spec(sid: str, name: str) -> None:
        sess = store.get_session(sid)
        state = dict(sess.context_state or {})
        state["spec"] = name
        store.update_session(sid, context_state=state, mode="spec")

    async def spec_create(request: Request) -> Response:
        ctx = ctx_for(request.path_params["sid"])
        data = await request.json()
        name = str(data.get("name") or "").strip() or specs.slug(str(data.get("description") or ""))
        try:
            spec = await run_in_threadpool(specs.create, ctx.root, name, str(data.get("kind") or "feature"))
        except FileExistsError as exc:
            return err(str(exc), 409)
        except ValueError as exc:
            return err(str(exc))
        set_active_spec(ctx.session_id, spec.name)
        return JSONResponse(spec.info(ctx.root), status_code=201)

    async def spec_action(request: Request) -> Response:
        ctx = ctx_for(request.path_params["sid"])
        spec = specs.get(ctx.root, request.path_params["name"])
        if spec is None:
            return err("No such spec", 404)
        action = request.path_params["action"]
        if action == "activate":
            set_active_spec(ctx.session_id, spec.name)
            return JSONResponse(spec.info(ctx.root))
        if action == "approve":
            phase = str((await request.json()).get("phase") or spec.phase)
            try:
                spec = specs.approve(ctx.root, spec, phase)
            except (ValueError, FileNotFoundError) as exc:
                return err(str(exc), 409)
            set_active_spec(ctx.session_id, spec.name)
            return JSONResponse(spec.info(ctx.root))
        return err("action must be activate or approve", 404)

    # -- steering docs ---------------------------------------------------------------------------

    def session_root(sid: str) -> Path | None:
        repo = store.get_session(sid).repo
        return Path(repo).expanduser().resolve() if repo and Path(repo).expanduser().is_dir() else None

    def steering_list(request: Request) -> Response:  # blocking I/O: runs in a worker thread
        try:
            root = session_root(request.path_params["sid"])
        except KeyError:
            return err("No such session", 404)
        return JSONResponse({"docs": [d.info(root) for d in steering.discover(root, cfg.home)],
                             "workspace_dir": ".codepilot/steering" if root else None,
                             "global_dir": str(cfg.home / "steering"), "foundation_prompt": steering.FOUNDATION_PROMPT})

    async def steering_create(request: Request) -> Response:
        data = await request.json()
        name = str(data.get("name") or "").strip().removesuffix(".md")
        inclusion = data.get("inclusion") if data.get("inclusion") in steering.INCLUSIONS else "always"
        pattern = str(data.get("pattern") or "").strip()
        if not steering.NAME.match(name):
            return err("Use letters, digits, - _ or . for the name (e.g. api-style).")
        if inclusion == "fileMatch" and not pattern:
            return err("Give a file pattern, e.g. src/api/**/*.ts")
        try:
            root = session_root(request.path_params["sid"])
        except KeyError:
            return err("No such session", 404)
        if data.get("scope") == "workspace":
            if root is None:
                return err("Open a folder first.", 409)
            path = root / ".codepilot" / "steering" / f"{name}.md"
        else:
            path = cfg.home / "steering" / f"{name}.md"
        if path.exists():
            return err(f"A steering doc named {name} already exists there.", 409)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(steering.template(name, inclusion, pattern))
        rel = str(path.relative_to(root)) if data.get("scope") == "workspace" else None
        return JSONResponse({"name": name, "rel": rel, "scope": "workspace" if rel else "global"})

    async def steering_global(request: Request) -> Response:
        """Read or save a doc in ~/.codepilot/steering (outside any workspace, so not via /fs)."""
        data = await request.json() if request.method == "PUT" else dict(request.query_params)
        name = str(data.get("name") or "")
        if not steering.NAME.match(name):
            return err("Bad steering doc name.")
        path = cfg.home / "steering" / f"{name}.md"
        if request.method == "GET":
            if not path.is_file():
                return err("No such steering doc", 404)
            return JSONResponse({"name": name, "path": str(path), "content": path.read_text(errors="replace"),
                                 "mtime": str(path.stat().st_mtime_ns)})
        if path.is_file() and data.get("base_mtime") and str(path.stat().st_mtime_ns) != str(data["base_mtime"]) \
                and not data.get("force"):
            return err(f"{name}.md changed on disk since you opened it.", 409)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(data.get("content") or ""))
        return JSONResponse({"name": name, "mtime": str(path.stat().st_mtime_ns)})

    RAW_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
                 ".webp": "image/webp", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".bmp": "image/bmp",
                 ".avif": "image/avif"}

    def raw_file(request: Request) -> Response:  # blocking I/O: runs in a worker thread
        """An image from the workspace, for Markdown previews and the image viewer. Images only, and served
        so it can never run script in this page's origin (an SVG can carry script)."""
        ctx = ctx_for(request.path_params["sid"])
        try:
            path = ctx.resolve(request.query_params.get("path", ""))
        except ToolError as exc:
            return err(str(exc), 404)
        media = RAW_TYPES.get(path.suffix.lower())
        if media is None or not path.is_file():
            return err("Only image files can be previewed", 415)
        if path.stat().st_size > 20_000_000:
            return err("Image too large to preview", 413)
        return Response(path.read_bytes(), media_type=media, headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})

    def git_view(request: Request) -> Response:  # blocking I/O: runs in a worker thread
        ctx = ctx_for(request.path_params["sid"])

        def run(*args: str) -> str:
            proc = subprocess.run(["git", "--no-pager", "-C", str(ctx.root), *args], capture_output=True,
                                  text=True, timeout=60, errors="replace")
            return proc.stdout if proc.returncode == 0 else ""  # never show git's error text as data

        if not (ctx.root / ".git").exists():
            return JSONResponse({"git": False})
        # symbolic-ref works before the first commit too; a detached HEAD shows its short hash.
        branch = run("symbolic-ref", "--short", "-q", "HEAD").strip() or run("rev-parse", "--short", "HEAD").strip()
        return JSONResponse({"git": True, "branch": branch,
                             "status": run("status", "--short"), "diff": run("diff")[:MAX_VIEW_BYTES]})

    async def notes(request: Request) -> Response:
        sess = store.get_session(request.path_params["sid"])
        if not sess.repo:
            raise ToolError("No workspace open in this session yet.")
        if request.method == "PUT":
            data = await request.json()
            path = store.notes_path(sess.repo)
            path.write_text(data.get("notes", ""))
        return JSONResponse({"notes": store.read_notes(sess.repo), "path": str(store.notes_path(sess.repo))})

    async def run(request: Request) -> Response:
        """User-initiated test/eval run from the UI (no model involved)."""
        sid = request.path_params["sid"]
        data = await request.json()
        kind = data.get("kind")
        if kind not in ("tests", "command", "checks"):
            return err("kind must be tests, checks or command")
        ctx = ctx_for(sid)
        if kind == "checks":
            started = time.time()
            output = await run_in_threadpool(checks.run_all, ctx.root)
            ok = "exit " not in output  # "no analysers found" is not a failure
            return JSONResponse({"output": output, "ok": ok, "seconds": round(time.time() - started, 1)})
        if kind == "tests":
            test_cmd = detect_test_cmd(ctx.root, cfg)
            if not test_cmd:
                return err("No test command detected; set CODEPILOT_TEST_CMD or use a custom command.")
            argv: list[str] | str = shlex.split(test_cmd) + shlex.split(data.get("args", ""))
        else:
            argv = (data.get("command") or "").strip()
            if not argv:
                return err("Enter a command.")
        started = time.time()
        try:
            output = await run_in_threadpool(_run_command, ctx, argv, 3600, kind)
            match = re.search(r"^exit code (-?\d+)", output, re.MULTILINE)
            ok = bool(match) and match.group(1) == "0"
        except ToolError as exc:
            output, ok = str(exc), False
        return JSONResponse({"output": output, "ok": ok, "seconds": round(time.time() - started, 1)})

    def needs_workspace(handler):
        async def wrapped(request: Request) -> Response:
            try:
                if inspect.iscoroutinefunction(handler):
                    return await handler(request)
                return await run_in_threadpool(handler, request)  # keep filesystem/git work off the event loop
            except ToolError as exc:
                return err(str(exc), 409)
            except KeyError:
                return err("No such session", 404)
        return wrapped

    routes = [
        Route("/", index),
        Mount("/static", app=StaticFiles(directory=STATIC), name="static"),
        Route("/api/config", config_view),
        Route("/api/restart", restart_view, methods=["POST"]),
        Route("/api/report", report_view, methods=["POST"]),
        Route("/api/images/{name}", image_view),
        Route("/api/browse", browse),
        Route("/api/github", github_view),
        Route("/api/models", models_view),
        WebSocketRoute("/api/terminal", terminal_ws),
        Route("/api/terminals", terminals_view, methods=["GET", "POST"]),
        Route("/api/terminals/{tid}", terminals_view, methods=["GET", "PATCH", "DELETE"]),
        Route("/api/sessions", sessions, methods=["GET", "POST"]),
        Route("/api/sessions/{sid}", session, methods=["GET", "PATCH", "DELETE"]),
        Route("/api/sessions/{sid}/chat", chat, methods=["POST"]),
        Route("/api/sessions/{sid}/approve", approve, methods=["POST"]),
        Route("/api/sessions/{sid}/cancel", cancel, methods=["POST"]),
        Route("/api/sessions/{sid}/queue", queue, methods=["GET", "POST"]),
        Route("/api/sessions/{sid}/queue/{qid}", queue, methods=["DELETE", "PATCH"]),
        Route("/api/sessions/{sid}/follow", follow),
        Route("/api/sessions/{sid}/rewind", rewind, methods=["POST"]),
        Route("/api/sessions/{sid}/compact", compact, methods=["POST"]),
        Route("/api/sessions/{sid}/handoff", handoff, methods=["POST"]),
        Route("/api/sessions/{sid}/grep", needs_workspace(grep)),
        Route("/api/sessions/{sid}/usage", usage),
        Route("/api/sessions/{sid}/workspace", needs_workspace(workspace_info)),
        Route("/api/sessions/{sid}/traces", needs_workspace(trace_list)),
        Route("/api/sessions/{sid}/trace", needs_workspace(trace_view)),
        Route("/api/sessions/{sid}/files", needs_workspace(files)),
        Route("/api/sessions/{sid}/find", needs_workspace(find)),
        Route("/api/sessions/{sid}/git", needs_workspace(git_view)),
        Route("/api/sessions/{sid}/fs", needs_workspace(fs), methods=["POST"]),
        Route("/api/sessions/{sid}/raw", needs_workspace(raw_file)),
        Route("/api/sessions/{sid}/specs", needs_workspace(spec_list)),
        Route("/api/sessions/{sid}/specs", needs_workspace(spec_create), methods=["POST"]),
        Route("/api/sessions/{sid}/specs/{name}/{action}", needs_workspace(spec_action), methods=["POST"]),
        Route("/api/sessions/{sid}/steering", steering_list),
        Route("/api/sessions/{sid}/steering", steering_create, methods=["POST"]),
        Route("/api/steering/global", steering_global, methods=["GET", "PUT"]),
        Route("/api/sessions/{sid}/notes", needs_workspace(notes), methods=["GET", "PUT"]),
        Route("/api/sessions/{sid}/run", needs_workspace(run), methods=["POST"]),
        Route("/api/proposals/{pid:int}/{action:str}", proposal_action, methods=["POST"]),
    ]
    middleware = [
        Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]),
        Middleware(_CsrfHeaderMiddleware),
    ]
    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield
        terminals.close_all()  # don't leave shells running after codepilot stops

    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
    app.state.terminals = terminals
    return app


class FileOpError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class _CsrfHeaderMiddleware:
    """Reject state-changing requests without our custom header. Browsers can't add it cross-site
    without a CORS preflight, which this app never grants, so other web pages can't drive it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            headers = dict(scope.get("headers") or [])
            if headers.get(b"x-codepilot") != b"1":
                await JSONResponse({"error": "missing X-Codepilot header"}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


PROJECT_MARKERS = (("pyproject.toml", "python"), ("setup.py", "python"), ("package.json", "node"),
                   ("go.mod", "go"), ("Cargo.toml", "rust"), ("pom.xml", "java"), ("build.gradle", "java"),
                   ("Gemfile", "ruby"), ("Makefile", "make"), (".git", "git"))


def _project_kind(path: Path) -> str | None:
    """A short label if the folder looks like a project root (shown as a badge in the folder browser)."""
    for marker, kind in PROJECT_MARKERS:
        try:
            if (path / marker).exists():
                return kind
        except OSError:
            return None
    return None


def _places(store: Store) -> list[dict]:
    home = Path.home()
    places = [{"name": "Home", "path": str(home)}]
    for name in ("Desktop", "Documents", "Downloads", "code", "src", "projects", "dev", "work", "repos", "git"):
        if (home / name).is_dir():
            places.append({"name": name, "path": str(home / name)})
    cloud = home / "Library" / "CloudStorage"
    if cloud.is_dir():
        for c in sorted(cloud.iterdir()):
            if c.is_dir() and not c.name.startswith("."):
                places.append({"name": c.name.replace("OneDrive-", "OneDrive · "), "path": str(c)})
    seen = set()
    for sess in store.list_sessions(30):
        if sess.repo and sess.repo not in seen and Path(sess.repo).is_dir():
            seen.add(sess.repo)
            places.append({"name": Path(sess.repo).name, "path": sess.repo, "recent": True})
    return places[:30]


def _proposal_json(prop, root: Path | None = None) -> dict:
    """Proposal with a full-context diff: from the saved before/after text once applied, else against the file."""
    if prop.after_text is not None:
        return proposal_view(prop, unified_diff(prop.path, prop.before_text or "", prop.after_text))
    if root is not None and prop.status == "pending":
        target = root / prop.path
        try:
            current = target.read_text() if target.exists() else ""
        except OSError:
            current = None
        if current is not None and (prop.old_text == "" and not current or current.count(prop.old_text) == 1):
            after = prop.new_text if prop.old_text == "" else current.replace(prop.old_text, prop.new_text, 1)
            return proposal_view(prop, unified_diff(prop.path, current, after))
    return proposal_view(prop, unified_diff(prop.path, prop.old_text, prop.new_text))
