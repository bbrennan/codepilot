"""Local web app: JSON API + NDJSON streaming for the chat, and the single-page UI."""

from __future__ import annotations

import json
import logging
import re
import secrets
import shlex
import subprocess
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

from . import checks, github, mentions, modes, skills, traces
from .agent import Agent, history_events
from .config import TIERS, Config
from .store import Store
from .tools import (
    SKIP_DIRS,
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
    term_token = secrets.token_urlsafe(32)  # new every launch; embedded in the page, required by /api/terminal

    def err(message: str, status: int = 400) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    def ctx_for(sid: str) -> ToolContext:
        sess = store.get_session(sid)
        root = Path(sess.repo).expanduser().resolve() if sess.repo else None
        if root is None:
            raise ToolError("No workspace open in this session yet.")
        return ToolContext(root=root, cfg=cfg, store=store, session_id=sid)

    def stream(sid: str, events: Iterator[dict]) -> Response:
        with busy_lock:
            if sid in busy:
                return err("This session is already working; wait for it to finish.", 409)
            busy.add(sid)

        def body() -> Iterator[bytes]:
            try:
                for event in events:
                    yield (json.dumps(event, default=str) + "\n").encode()
            except Exception as exc:  # surface unexpected failures in the chat instead of a dead stream
                log.error("agent failure:\n%s", traceback.format_exc())
                yield (json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"}) + "\n").encode()
                yield (json.dumps({"type": "done"}) + "\n").encode()
            finally:
                with busy_lock:
                    busy.discard(sid)

        return StreamingResponse(body(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def index(request: Request) -> Response:
        html = (STATIC / "index.html").read_text().replace("__CODEPILOT_TOKEN__", term_token if cfg.terminal else "")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    async def terminal_ws(ws: WebSocket) -> None:
        from . import terminal

        headers = {k.decode().lower(): v.decode() for k, v in ws.scope.get("headers", [])}
        origin_host = headers.get("origin", "").split("://", 1)[-1]
        allowed = cfg.terminal and secrets.compare_digest(ws.query_params.get("token", ""), term_token) \
            and origin_host == headers.get("host", "")
        if not allowed:
            await ws.close(code=1008)  # policy violation: wrong token, wrong origin, or terminal disabled
            return
        cwd = Path.home()
        sid = ws.query_params.get("sid")
        if sid:
            try:
                repo = store.get_session(sid).repo
                if repo and Path(repo).is_dir():
                    cwd = Path(repo)
            except KeyError:
                pass
        await ws.accept()
        await terminal.serve(ws, cwd)

    async def config_view(request: Request) -> Response:
        return JSONResponse({
            "provider": cfg.provider, "models": cfg.models, "tiers": list(TIERS), "default_tier": cfg.default_tier,
            "default_repo": cfg.default_repo, "test_cmd": cfg.test_cmd or "(auto-detect)", "eval_cmd": cfg.eval_cmd,
            "region": cfg.region if cfg.provider == "bedrock" else None,
            "profile": cfg.profile if cfg.provider == "bedrock" else None,
            "log_groups": cfg.log_groups, "auto_approve_default": cfg.auto_approve_tests, "terminal": cfg.terminal,
            "home": str(Path.home()),
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
        if tier not in TIERS:
            return err(f"tier must be one of {TIERS}")
        sess = store.create_session(repo, tier, auto_approve=bool(data.get("auto_approve", False)))
        return JSONResponse(sess.public())

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
            fields = {k: data[k] for k in ("title", "tier", "auto_approve", "repo", "mode") if k in data}
            if "mode" in fields:
                root_ = Path(sess.repo).expanduser().resolve() if sess.repo else None
                known = {m.name for m in modes.all_modes(root_, cfg.home)} | set(modes.ALIASES)
                if fields["mode"] not in known:
                    return err(f"unknown mode; choose one of {sorted(known)}")
            if "tier" in fields and fields["tier"] not in TIERS:
                return err(f"tier must be one of {TIERS}")
            if "repo" in fields:
                path = Path(str(fields["repo"])).expanduser().resolve()
                if not path.is_dir():
                    return err(f"Not a directory: {path}")
                fields["repo"] = str(path)
            if fields:
                store.update_session(sid, **fields)
            sess = store.get_session(sid)
        root = Path(sess.repo).expanduser().resolve() if sess.repo else None
        return JSONResponse({
            "session": sess.public(),
            "summary": sess.summary,
            "events": history_events(store, sid),
            "pending": sess.pending and [{"id": tu["toolUseId"], "name": tu["name"], "input": tu["input"],
                                          "command": agent.describe(tu, root)} for tu in sess.pending["awaiting"]],
            "proposals": [_proposal_json(p, root) for p in store.list_proposals(sid)],
            "usage": store.usage(sid),
            "context": agent.context_usage(sid),
        })

    async def chat(request: Request) -> Response:
        sid = request.path_params["sid"]
        data = await request.json()
        text = (data.get("message") or "").strip()
        if not text:
            return err("Empty message")
        tier = data.get("tier")
        if tier and tier not in TIERS:
            return err(f"tier must be one of {TIERS}")
        try:
            store.get_session(sid)
        except KeyError:
            return err("No such session", 404)
        return stream(sid, agent.chat(sid, text, tier))

    gh_status: dict = {}

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
        agent.cancel(request.path_params["sid"])
        return JSONResponse({"ok": True})

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
        return stream(sid, agent.resume(sid, bool(data.get("approve"))))

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
        return JSONResponse({**_proposal_json(store.get_proposal(pid), root), "checks": found})

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
                             "instructions": skills.project_instructions(root, cfg.home)[:4000]})

    async def browse(request: Request) -> Response:
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

    async def trace_list(request: Request) -> Response:
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

    async def trace_view(request: Request) -> Response:
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

    async def files(request: Request) -> Response:
        ctx = ctx_for(request.path_params["sid"])
        try:
            base = ctx.resolve(request.query_params.get("path", "."))
        except ToolError as exc:
            return err(str(exc), 404)
        if base.is_file():
            if base.stat().st_size > MAX_VIEW_BYTES:
                return err("File too large to view")
            return JSONResponse({"path": ctx.rel(base), "content": base.read_text(errors="replace")})
        entries = []
        for p in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if p.name in SKIP_DIRS or p.name == ".DS_Store":
                continue
            entries.append({"name": p.name, "path": ctx.rel(p), "dir": p.is_dir()})
        return JSONResponse({"path": ctx.rel(base), "entries": entries})

    async def git_view(request: Request) -> Response:
        ctx = ctx_for(request.path_params["sid"])

        def run(*args: str) -> str:
            proc = subprocess.run(["git", "--no-pager", "-C", str(ctx.root), *args], capture_output=True,
                                  text=True, timeout=60, errors="replace")
            return proc.stdout if proc.returncode == 0 else proc.stderr

        if not (ctx.root / ".git").exists():
            return JSONResponse({"git": False})
        return JSONResponse({"git": True, "branch": run("rev-parse", "--abbrev-ref", "HEAD").strip(),
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
                return await handler(request)
            except ToolError as exc:
                return err(str(exc), 409)
            except KeyError:
                return err("No such session", 404)
        return wrapped

    routes = [
        Route("/", index),
        Mount("/static", app=StaticFiles(directory=STATIC), name="static"),
        Route("/api/config", config_view),
        Route("/api/browse", browse),
        Route("/api/github", github_view),
        WebSocketRoute("/api/terminal", terminal_ws),
        Route("/api/sessions", sessions, methods=["GET", "POST"]),
        Route("/api/sessions/{sid}", session, methods=["GET", "PATCH", "DELETE"]),
        Route("/api/sessions/{sid}/chat", chat, methods=["POST"]),
        Route("/api/sessions/{sid}/approve", approve, methods=["POST"]),
        Route("/api/sessions/{sid}/cancel", cancel, methods=["POST"]),
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
        Route("/api/sessions/{sid}/notes", needs_workspace(notes), methods=["GET", "PUT"]),
        Route("/api/sessions/{sid}/run", needs_workspace(run), methods=["POST"]),
        Route("/api/proposals/{pid:int}/{action:str}", proposal_action, methods=["POST"]),
    ]
    middleware = [
        Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]),
        Middleware(_CsrfHeaderMiddleware),
    ]
    return Starlette(routes=routes, middleware=middleware)


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
