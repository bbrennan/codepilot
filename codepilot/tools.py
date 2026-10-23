"""Tools the model can call. File access is confined to the session's workspace directory."""

from __future__ import annotations

import difflib
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import checks, github, images, skills, specs, steering, traces, webtools
from .config import Config
from .store import Store

MAX_OUTPUT = 20_000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
             ".ruff_cache", "dist", "build", ".tox", ".idea", ".vscode", "cdk.out", ".aws-sam"}
TRACE_DIR_NAMES = {"traces", "trace", "logs", "log", ".traces", "journeys", "eval_results", "results"}
TRACE_SUFFIXES = {".json", ".jsonl", ".ndjson", ".log", ".txt"}
GIT_READONLY = {"status", "diff", "log", "show", "blame", "branch", "rev-parse", "ls-files", "shortlog"}
GIT_BANNED_ARGS = ("--output", "--exec", "-c", "--git-dir", "--work-tree", "--ext-diff")


class ToolError(Exception):
    """A tool failed in a way the model should see and can recover from."""


@dataclass
class ToolContext:
    root: Path | None  # None until the user names a workspace
    cfg: Config
    store: Store
    session_id: str
    logs_client_factory: Callable[[], Any] | None = None
    events: list[dict] = field(default_factory=list)
    auto_apply: bool = False  # this session writes edits immediately (CODEPILOT_AUTO_APPLY does it everywhere)

    def resolve(self, rel: str | None, must_exist: bool = True) -> Path:
        if self.root is None:
            raise ToolError("no workspace open yet; ask the user which directory to work in, then open_workspace")
        rel = (rel or ".").strip() or "."
        path = Path(rel).expanduser()
        path = (path if path.is_absolute() else self.root / path).resolve()
        if path != self.root and self.root not in path.parents:
            raise ToolError(f"{rel!r} is outside the repository")
        if must_exist and not path.exists():
            raise ToolError(f"{rel!r} does not exist")
        return path

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)) if path != self.root else "."


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., str] | None
    needs_approval: bool = False
    needs_workspace: bool = True
    read_only: bool = True  # read-only tools are available to the explore sub-agent
    approval_fn: Callable[[dict], bool] | None = None  # per-call approval decision (e.g. gh read vs write)
    auto_approvable: bool = False  # the session's "auto-run" switch skips approval (tests, checks)

    def requires_approval(self, tool_input: dict, auto_run: bool) -> bool:
        if self.approval_fn is not None:
            return self.approval_fn(tool_input)
        if self.auto_approvable and auto_run:
            return False
        return self.needs_approval

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": {"json": self.schema}}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


def clip(text: str, limit: int = MAX_OUTPUT, tail: bool = False) -> str:
    if len(text) <= limit:
        return text
    cut = len(text) - limit
    if tail:
        return f"[... {cut} earlier characters omitted ...]\n" + text[-limit:]
    return text[:limit] + f"\n[... {cut} more characters omitted; narrow the request ...]"


def _iter_files(ctx: ToolContext, base: Path) -> list[Path]:
    """Files under base, honouring .gitignore when the repo is a git checkout."""
    if (ctx.root / ".git").exists():
        proc = subprocess.run(
            ["git", "-C", str(ctx.root), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
             ctx.rel(base)],
            capture_output=True, timeout=60,
        )
        if proc.returncode == 0:
            files = [ctx.root / p for p in proc.stdout.decode(errors="replace").split("\0") if p]
            return [f for f in files if f.is_file()]
    if base.is_file():
        return [base]
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        out += [Path(dirpath) / f for f in sorted(filenames)]
    return out


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return b"\0" in fh.read(4096)
    except OSError:
        return True


# -- tool implementations -------------------------------------------------------------------------


def list_files(ctx: ToolContext, path: str = ".", pattern: str = "", limit: int = 400) -> str:
    base = ctx.resolve(path)
    files = [ctx.rel(f) for f in _iter_files(ctx, base)]
    if pattern:
        files = [f for f in files if fnmatch.fnmatch(f, pattern) or fnmatch.fnmatch(Path(f).name, pattern)]
    total = len(files)
    lines = files[: max(1, min(limit, 2000))]
    suffix = f"\n[{total - len(lines)} more files not shown]" if total > len(lines) else ""
    return ("\n".join(lines) or "(no files)") + suffix


def read_file(ctx: ToolContext, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    target = ctx.resolve(path)
    if target.is_dir():
        raise ToolError(f"{path!r} is a directory; use list_files")
    if _is_binary(target):
        raise ToolError(f"{path!r} looks binary")
    lines = target.read_text(errors="replace").splitlines()
    start = max(1, start_line)
    end = min(len(lines), end_line or start + 499)
    if start > len(lines):
        return f"(file has {len(lines)} lines)"
    body = "\n".join(f"{n:>5}  {lines[n - 1]}" for n in range(start, end + 1))
    more = f"\n[file has {len(lines)} lines; showing {start}-{end}]" if end < len(lines) or start > 1 else ""
    return clip(body + more)


def _rg_search(ctx: ToolContext, base: Path, pattern: str, glob: str, max_results: int) -> str | None:
    """ripgrep when installed: much faster on big repos and respects .gitignore. None means fall back."""
    rg = shutil.which("rg")
    if not rg:
        return None
    argv = [rg, "-n", "--no-heading", "--color", "never", "--max-columns", "300", "-e", pattern]
    if glob:
        argv += ["--glob", glob]
    argv += ["--", ctx.rel(base)]
    try:
        proc = subprocess.run(argv, cwd=ctx.root, capture_output=True, text=True, timeout=60, errors="replace",
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 1:
        return "(no matches)"
    if proc.returncode != 0:
        return None  # e.g. a regex rg doesn't support; the Python engine will try
    lines = proc.stdout.splitlines()
    out = [f"{ln.split(':', 2)[0].removeprefix('./')}:{ln.split(':', 2)[1]}: {ln.split(':', 2)[2]}"
           for ln in lines[:max_results] if ln.count(":") >= 2]
    more = "\n[result limit reached; narrow the search]" if len(lines) > max_results else ""
    return "\n".join(out) + more


def search_code(ctx: ToolContext, pattern: str, path: str = ".", glob: str = "", max_results: int = 100) -> str:
    base = ctx.resolve(path)
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ToolError(f"invalid regex: {exc}") from exc
    fast = _rg_search(ctx, base, pattern, glob, max_results)
    if fast is not None:
        return fast
    hits: list[str] = []
    for file in _iter_files(ctx, base):
        rel = ctx.rel(file)
        if glob and not (fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(file.name, glob)):
            continue
        if _is_binary(file):
            continue
        try:
            with file.open(errors="replace") as fh:
                for n, line in enumerate(fh, 1):
                    if regex.search(line):
                        hits.append(f"{rel}:{n}: {line.rstrip()[:300]}")
                        if len(hits) >= max_results:
                            return "\n".join(hits) + "\n[result limit reached; narrow the search]"
        except OSError:
            continue
    return "\n".join(hits) or "(no matches)"


def git(ctx: ToolContext, args: str) -> str:
    argv = shlex.split(args)
    if not argv or argv[0] not in GIT_READONLY:
        raise ToolError(f"only read-only git subcommands are allowed: {sorted(GIT_READONLY)}")
    for arg in argv:
        if arg in GIT_BANNED_ARGS or any(arg.startswith(b + "=") for b in GIT_BANNED_ARGS):
            raise ToolError(f"git argument {arg!r} is not allowed")
    proc = subprocess.run(["git", "--no-pager", "-C", str(ctx.root), *argv], capture_output=True, text=True,
                          timeout=120, errors="replace")
    out = proc.stdout + (f"\n[stderr]\n{proc.stderr}" if proc.stderr.strip() else "")
    if proc.returncode != 0:
        raise ToolError(clip(out or f"git exited {proc.returncode}"))
    return clip(out or "(no output)")


def _run_command(ctx: ToolContext, argv: list[str] | str, timeout: int, what: str) -> str:
    """Run argv (or a shell string via bash -c) in the workspace and return a header plus clipped output."""
    if isinstance(argv, str):
        shown, argv = argv, ["/bin/bash", "-c", argv]
    else:
        if shutil.which(argv[0]) is None:
            raise ToolError(f"{what} command {argv[0]!r} not found on PATH")
        shown = shlex.join(argv)
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)  # don't leak codepilot's own venv into the workspace's tooling
    started = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=ctx.root, capture_output=True, text=True, timeout=timeout, env=env,
                              errors="replace")
    except subprocess.TimeoutExpired:
        raise ToolError(f"{what} timed out after {timeout}s") from None
    took = time.monotonic() - started
    header = f"$ {shown}\nexit code {proc.returncode} in {took:.1f}s\n"
    return header + clip(proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr.strip() else ""), tail=True)


def detect_test_cmd(root: Path | None, cfg: Config) -> str:
    """CODEPILOT_TEST_CMD if set, else a guess from the workspace's build files ('' if none)."""
    if cfg.test_cmd:
        return cfg.test_cmd
    if root is None:
        return ""
    def has(name: str) -> bool:
        return (root / name).exists()

    if has("pyproject.toml") or has("pytest.ini") or has("setup.py") or has("tests"):
        return "uv run pytest -q" if has("uv.lock") else "python3 -m pytest -q"
    if has("package.json"):
        return "npm test --silent"
    if has("go.mod"):
        return "go test ./..."
    if has("Cargo.toml"):
        return "cargo test"
    if has("Makefile") and any(line.startswith("test:") for line in (root / "Makefile").read_text().splitlines()):
        return "make test"
    return ""


def run_tests(ctx: ToolContext, args: str = "") -> str:
    cmd = detect_test_cmd(ctx.root, ctx.cfg)
    if not cmd:
        raise ToolError("no test command known for this workspace; use run_command with the right command")
    return _run_command(ctx, shlex.split(cmd) + shlex.split(args), 900, "test")


def run_command(ctx: ToolContext, command: str, timeout_seconds: int = 600) -> str:
    return _run_command(ctx, command, max(5, min(timeout_seconds, 3600)), "command")


def open_workspace(ctx: ToolContext, path: str) -> str:
    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        raise ToolError(f"{target} is not a directory")
    ctx.store.update_session(ctx.session_id, repo=str(target))
    ctx.root = target
    ctx.events.append({"type": "workspace", "repo": str(target)})
    entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir() if p.name not in SKIP_DIRS)
    test = detect_test_cmd(target, ctx.cfg)
    return (f"Workspace is now {target}.\nTop-level entries: {', '.join(entries[:80])}\n"
            f"Detected test command: {test or '(none)'}")


def update_plan(ctx: ToolContext, items: list) -> str:
    clean = []
    for item in items:
        if isinstance(item, str):
            item = {"text": item}
        status = item.get("status", "todo")
        clean.append({"text": str(item.get("text", ""))[:300],
                      "status": status if status in ("todo", "doing", "done") else "todo"})
    ctx.events.append({"type": "plan", "items": clean})
    return "Plan updated."


def load_skill(ctx: ToolContext, name: str) -> str:
    skill = skills.find(name, ctx.root, ctx.cfg.home)
    if skill is None:
        doc = steering.find(name, ctx.root, ctx.cfg.home)
        if doc is not None:
            return steering.render(doc, ctx.root, "loaded on request")
    if skill is not None and skill.user_only:
        raise ToolError(f"{name!r} is a user-invoked skill (the user runs it with /{name})")
    if skill is None:
        names = ", ".join(sk.name for sk in skills.discover(ctx.root, ctx.cfg.home))
        raise ToolError(f"no skill named {name!r}; available: {names}")
    return skill.body


def github_cli(ctx: ToolContext, args: str) -> str:
    argv = shlex.split(args.removeprefix("gh ").strip())
    kind = github.classify(argv)
    if kind is None:
        raise ToolError("not an allowed gh command. Read: pr list/view/diff/checks, issue list/view, run list/view "
                        "(--log-failed), repo view, search ..., api <GET endpoint>. With approval: pr create/comment/"
                        "review/edit/checkout, issue create/comment/edit, run rerun, api writes.")
    code, out = github.run(ctx.root or Path.home(), shlex.join(argv), ctx.cfg.github_host)
    if code != 0:
        raise ToolError(clip(out or f"gh exited {code}"))
    return clip(github.pretty(out) or "(no output)")


def run_checks(ctx: ToolContext, kind: str = "all", paths: str = "") -> str:
    if kind not in ("all", "lint", "types", "security"):
        raise ToolError("kind must be all, lint, types or security")
    targets = [str(ctx.resolve(p).relative_to(ctx.root)) for p in shlex.split(paths)] if paths else None
    return clip(checks.run_all(ctx.root, kind, targets))


def scratch_dir(ctx: ToolContext) -> Path:
    d = ctx.cfg.home / "scratch" / ctx.session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_scratch(ctx: ToolContext, name: str, content: str) -> str:
    """Write a throwaway file (repro script, harness, fixture) outside the workspace."""
    base = scratch_dir(ctx).resolve()
    target = (base / name).resolve()
    if target == base or base not in target.parents:
        raise ToolError("scratch file name must stay inside the scratch folder")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return (f"Wrote {len(content)} chars to {target}\nRun it with run_command, e.g. `python3 {target}` "
            "(the command runs in the workspace root, so imports of workspace code resolve).")


def trace_outline(ctx: ToolContext, path: str) -> str:
    return clip(traces.outline_text(_locate_trace(ctx, path)))


def trace_roots(ctx: ToolContext) -> list[Path]:
    """Configured trace directories, or conventional ones (traces/, logs/, ...) found near the top of the repo."""
    if ctx.cfg.trace_dirs:
        roots = []
        for d in ctx.cfg.trace_dirs:
            p = Path(d).expanduser()
            p = (p if p.is_absolute() else ctx.root / p).resolve()
            if p.exists():
                roots.append(p)
        return roots
    found = []
    for dirpath, dirnames, _ in os.walk(ctx.root):
        depth = len(Path(dirpath).relative_to(ctx.root).parts)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for d in list(dirnames):
            if d.lower() in TRACE_DIR_NAMES:
                found.append(Path(dirpath) / d)
                dirnames.remove(d)
        if depth >= 3:
            dirnames[:] = []
    return found


def _trace_files(ctx: ToolContext) -> list[Path]:
    files = []
    for root in trace_roots(ctx):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [Path(dirpath) / f for f in filenames if Path(f).suffix.lower() in TRACE_SUFFIXES]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _display(ctx: ToolContext, path: Path) -> str:
    try:
        return ctx.rel(path)
    except ValueError:
        return str(path)


def search_traces(ctx: ToolContext, query: str, max_results: int = 40) -> str:
    files = _trace_files(ctx)
    if not files:
        return "(no trace/log files found; set CODEPILOT_TRACE_DIRS, or use cloudwatch_logs if configured)"
    try:
        regex = re.compile(query, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(query), re.IGNORECASE)
    hits = []
    for file in files:
        try:
            with file.open(errors="replace") as fh:
                for n, line in enumerate(fh, 1):
                    if regex.search(line):
                        hits.append(f"{_display(ctx, file)}:{n}: {line.strip()[:1500]}")
                        if len(hits) >= max_results:
                            return clip("\n".join(hits) + "\n[result limit reached; narrow the query]")
        except OSError:
            continue
    return clip("\n".join(hits)) if hits else f"(no matches in {len(files)} trace/log files)"


def list_traces(ctx: ToolContext, limit: int = 100) -> str:
    files = _trace_files(ctx)
    if not files:
        return "(no trace/log files found; set CODEPILOT_TRACE_DIRS)"
    rows = []
    for f in files[:limit]:
        st = f.stat()
        rows.append(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}  {st.st_size:>10,}  "
                    f"{_display(ctx, f)}")
    more = f"\n[{len(files) - limit} more]" if len(files) > limit else ""
    return "modified          bytes  file (newest first)\n" + "\n".join(rows) + more


def _locate_trace(ctx: ToolContext, path: str) -> Path:
    """Resolve a trace path inside the repo or a configured trace dir (which may live outside the repo)."""
    p = Path(path).expanduser()
    roots = trace_roots(ctx)
    candidates = [p] if p.is_absolute() else [ctx.root / p] + [r / p for r in roots]
    allowed = [ctx.root, *roots]
    for cand in candidates:
        cand = cand.resolve()
        if cand.is_file() and any(cand == a or a in cand.parents for a in allowed):
            return cand
    raise ToolError(f"trace file {path!r} not found in the repo or trace directories")


def read_trace(ctx: ToolContext, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    target = _locate_trace(ctx, path)
    lines = target.read_text(errors="replace").splitlines()
    if len(lines) == 1 and target.suffix.lower() == ".json":
        # Minified JSON: pretty-print so line ranges are meaningful.
        try:
            lines = json.dumps(json.loads(lines[0]), indent=1).splitlines()
        except json.JSONDecodeError:
            pass
    end = min(len(lines), end_line or start_line + 199)
    body = "\n".join(f"{n:>5}  {lines[n - 1][:4000]}" for n in range(max(1, start_line), end + 1))
    return clip(body + f"\n[{len(lines)} lines total]")


def cloudwatch_logs(ctx: ToolContext, log_group: str, filter_pattern: str = "", hours: float = 24,
                    limit: int = 50) -> str:
    if not any(log_group == g or (g.endswith("*") and log_group.startswith(g[:-1])) for g in ctx.cfg.log_groups):
        raise ToolError(f"log group not allowed; configured groups: {ctx.cfg.log_groups}")
    if ctx.logs_client_factory is None:
        raise ToolError("CloudWatch client unavailable")
    client = ctx.logs_client_factory()
    start = int((time.time() - hours * 3600) * 1000)
    kwargs: dict[str, Any] = {"logGroupName": log_group, "startTime": start, "limit": min(limit, 200)}
    if filter_pattern:
        kwargs["filterPattern"] = filter_pattern
    try:
        resp = client.filter_log_events(**kwargs)
    except Exception as exc:
        raise ToolError(f"CloudWatch error: {exc}") from exc
    events = resp.get("events", [])
    if not events:
        return "(no matching events)"
    rows = [f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(e['timestamp'] / 1000))}Z "
            f"[{e.get('logStreamName', '')[-24:]}] {e['message'].strip()[:3000]}" for e in events]
    return clip("\n".join(rows))


def propose_edit(ctx: ToolContext, path: str, old_text: str, new_text: str, reason: str = "") -> str:
    target = ctx.resolve(path, must_exist=False)
    if target.exists():
        content = target.read_text(errors="replace")
        if old_text == "":
            raise ToolError("old_text is empty but the file exists; quote the exact text to replace")
        count = content.count(old_text)
        if count == 0:
            raise ToolError("old_text not found in file; re-read the file and quote it exactly (including indentation)")
        if count > 1:
            raise ToolError(f"old_text occurs {count} times; include more surrounding lines so it is unique")
        after = content.replace(old_text, new_text, 1)
    else:
        if old_text != "":
            raise ToolError(f"{path!r} does not exist; to create it pass old_text as an empty string")
        content, after = "", new_text
    rel = ctx.rel(target)
    proposal = ctx.store.add_proposal(ctx.session_id, rel, old_text, new_text, reason)
    diff = unified_diff(rel, content, after)
    if ctx.cfg.auto_apply_edits or ctx.auto_apply:
        before, written = apply_proposal(ctx.root, proposal)
        found = checks.quick_check(ctx.root, rel)
        ctx.store.record_applied(proposal.id, before, written, found)
        ctx.store.take_unreported_outcomes(ctx.session_id)  # the model hears it here, not next turn
        proposal = ctx.store.get_proposal(proposal.id)
        ctx.events.append({"type": "proposal", "proposal": proposal_view(proposal, diff)})
        note = f"\nAutomatic checks on the file found:\n{found}" if found else ""
        return f"Applied change #{proposal.id} to {rel} (auto-apply is on; the user can undo it).{note}"
    ctx.events.append({"type": "proposal", "proposal": proposal_view(proposal, diff)})
    return f"Proposed change #{proposal.id} to {rel} (pending the user's approval; not yet applied)."


def recall(ctx: ToolContext, query: str, scope: str = "session", limit: int = 6) -> str:
    hits = ctx.store.search_history(ctx.session_id, query, scope if scope in ("session", "workspace") else "session",
                                    max(1, min(int(limit or 6), 15)))
    if not hits:
        where = "this session's compacted history" if scope != "workspace" else "earlier history for this folder"
        return f"No matches in {where}. The current conversation is already in context."
    out = []
    for h in hits:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(h["created"]))
        src = "" if h["session_id"] == ctx.session_id else f", session '{h['session_title'] or h['session_id'][:8]}'"
        out.append(f"--- {h['role']} message #{h['message_id']} ({when}{src})\n{h['text']}")
    return "\n".join(out)


def _active_spec(ctx: ToolContext):
    name = (ctx.store.get_session(ctx.session_id).context_state or {}).get("spec")
    spec = specs.get(ctx.root, name) if name and ctx.root else None
    if spec is None:
        raise ToolError("No spec is active. The user starts one in the Specs view or in Spec mode.")
    return spec


def write_spec(ctx: ToolContext, doc: str, content: str) -> str:
    spec = _active_spec(ctx)
    if doc not in specs.PHASES[:3]:
        raise ToolError("doc must be requirements, design or tasks")
    phase = spec.phase
    if specs.PHASES.index(doc) > specs.PHASES.index(phase):
        raise ToolError(f"The spec is in the {phase} phase; the user approves it before you write {doc}.")
    path = spec.doc(doc)
    path.write_text(content.rstrip() + "\n")
    rel = ctx.rel(path)
    ctx.events.append({"type": "spec", "name": spec.name, "doc": doc, "path": rel})
    return f"Wrote {rel}. Ask the user to review it in the Spec tab." if phase != "implement" else f"Updated {rel}."


def update_task(ctx: ToolContext, task: str, status: str) -> str:
    spec = _active_spec(ctx)
    if spec.phase != "implement":
        raise ToolError("Tasks are tracked once the task list is approved.")
    if status not in ("todo", "in_progress", "done"):
        raise ToolError("status must be todo, in_progress or done")
    try:
        t = specs.set_task_status(spec.doc("tasks"), str(task), status)
    except KeyError as exc:
        raise ToolError(str(exc)) from None
    ctx.events.append({"type": "spec", "name": spec.name, "task": t.id, "status": status})
    return f"Task {t.id} ({t.title}) is now {status}."


class WithImages(str):
    """A tool result that also carries images (see view_image)."""

    images: list[dict]


def view_image(ctx: ToolContext, source: str) -> str:
    """Look at an image: a file in the workspace or an http(s) URL."""
    source = source.strip()
    try:
        if re.match(r"https?://", source, re.I):
            data = images.fetch(source)
        else:
            data = images.load_path(ctx.resolve(source))
        img = images.block(data)
    except images.ImageError as exc:
        raise ToolError(str(exc)) from None
    out = WithImages(f"Image {source} ({img['image']['format']}, {len(data) / 1024:.0f} KB) is attached below.")
    out.images = [img]
    return out


def library_docs(ctx: ToolContext, library: str, question: str) -> str:
    try:
        return webtools.library_docs(library, question, ctx.cfg.context7_api_key)
    except webtools.WebError as exc:
        raise ToolError(str(exc)) from None


def web_fetch(ctx: ToolContext, url: str) -> str:
    try:
        page = webtools.fetch_page(url.strip())
    except webtools.WebError as exc:
        raise ToolError(str(exc)) from None
    if page["kind"] == "image":
        try:
            img = images.block(page["bytes"])
        except images.ImageError as exc:
            raise ToolError(str(exc)) from None
        out = WithImages(f"Image from {page['url']} is attached below.")
        out.images = [img]
        return out
    head = f"# {page['title']}\n" if page["title"] else ""
    return f"{head}Source: {page['url']}\n\n{page['text']}"


def web_search(ctx: ToolContext, query: str) -> str:
    try:
        return webtools.web_search(query, ctx.cfg.brave_api_key)
    except webtools.WebError as exc:
        raise ToolError(str(exc)) from None


def remember(ctx: ToolContext, note: str) -> str:
    ctx.store.add_note(str(ctx.root), note)
    return "Saved to this workspace's notes."


# -- proposals ------------------------------------------------------------------------------------


def unified_diff(rel: str, before: str, after: str) -> str:
    def lines(text: str) -> list[str]:
        # Terminate every line so a missing final newline can't glue a - line to the next + line.
        return [ln if ln.endswith("\n") else ln + "\n" for ln in text.splitlines(keepends=True)]

    return "".join(difflib.unified_diff(lines(before), lines(after), fromfile=f"a/{rel}", tofile=f"b/{rel}"))


def proposal_view(proposal, diff: str) -> dict:
    return {"id": proposal.id, "path": proposal.path, "reason": proposal.reason, "status": proposal.status,
            "diff": diff}


def apply_proposal(root: Path, proposal) -> tuple[str | None, str]:
    """Write an approved proposal to disk, re-validating against the current file. Returns (before, after);
    before is None when the proposal created the file."""
    target = (root / proposal.path).resolve()
    if target != root and root not in target.parents:
        raise ToolError("proposal path escapes the repository")
    if proposal.old_text == "":
        if target.exists():
            raise ToolError(f"{proposal.path} now exists; refusing to overwrite")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proposal.new_text)
        return None, proposal.new_text
    content = target.read_text()
    count = content.count(proposal.old_text)
    if count != 1:
        raise ToolError(f"{proposal.path} changed since the proposal (old text found {count} times); ask for a new one")
    after = content.replace(proposal.old_text, proposal.new_text, 1)
    target.write_text(after)
    return content, after


def revert_proposal(root: Path, proposal) -> None:
    """Undo an applied proposal, but only if the file still holds exactly what the proposal wrote."""
    if proposal.status != "applied" or proposal.after_text is None:
        raise ToolError("only applied changes can be undone")
    target = (root / proposal.path).resolve()
    if target != root and root not in target.parents:
        raise ToolError("proposal path escapes the repository")
    if not target.exists() or target.read_text() != proposal.after_text:
        raise ToolError(f"{proposal.path} has changed since it was applied; undo it by hand or ask codepilot")
    if proposal.before_text is None:
        target.unlink()
    else:
        target.write_text(proposal.before_text)


# -- registry -------------------------------------------------------------------------------------


def build_tools(cfg: Config) -> list[Tool]:
    s, i, n = {"type": "string"}, {"type": "integer"}, {"type": "number"}
    tools = [
        Tool("open_workspace", "Switch this session to a directory on this machine (absolute path or ~/...). "
             "Call it when the user names a codebase to work on. The user approves the switch.",
             _obj({"path": s}, ["path"]), open_workspace, needs_approval=True, needs_workspace=False),
        Tool("list_files", "List files in the workspace (respects .gitignore). Use `pattern` (glob) to filter, "
             "e.g. '*.py' or 'tests/*'.",
             _obj({"path": {**s, "description": "Directory relative to the workspace root"}, "pattern": s,
                   "limit": i}), list_files),
        Tool("read_file", "Read a file with line numbers. Reads 500 lines by default; use start_line/end_line "
             "for more.", _obj({"path": s, "start_line": i, "end_line": i}, ["path"]), read_file),
        Tool("search_code", "Regex search over workspace files (Python `re` syntax). Returns file:line: text.",
             _obj({"pattern": s, "path": s, "glob": {**s, "description": "e.g. '*.py'"}, "max_results": i},
                  ["pattern"]), search_code),
        Tool("git", "Run a read-only git command in the workspace, e.g. 'status', 'diff main...HEAD', "
             "'log --oneline -20', 'show HEAD~1:path', 'blame -L 10,40 file.py'.",
             _obj({"args": s}, ["args"]), git),
        Tool("explore", "Delegate a read-only investigation to a sub-agent on the fast model, e.g. 'find where "
             "retries are configured and list every caller'. It reads files, searches, and inspects traces, then "
             "returns a concise report with file:line citations. Use it for broad searches so the main "
             "conversation stays small; run several in one turn for independent questions.",
             _obj({"task": {**s, "description": "What to find out and what to report back"}}, ["task"]), None),
        Tool("run_tests", "Run the workspace's test suite (CODEPILOT_TEST_CMD, else detected from build files), "
             "optionally with extra arguments such as a test path or '-k name'.",
             _obj({"args": {**s, "description": "Extra arguments appended to the test command"}}),
             run_tests, needs_approval=not cfg.auto_approve_tests, auto_approvable=True, read_only=False),
        Tool("run_checks", "Run the workspace's deterministic analysers: linters, type checkers and security "
             "scanners that are installed (e.g. ruff, mypy, pyright, eslint, tsc, go vet, clippy, bandit, gitleaks, "
             "semgrep). Ground truth: use it before and after changes, and in reviews and bug hunts.",
             _obj({"kind": {"type": "string", "enum": ["all", "lint", "types", "security"]},
                   "paths": {**s, "description": "Optional space-separated paths to limit the run"}}),
             run_checks, needs_approval=True, auto_approvable=True, read_only=False),
        Tool("run_command", "Run a shell command (bash) in the workspace root, e.g. a build, linter, eval or "
             "script. The user sees the exact command and approves each run. Don't use it to edit files; "
             "use propose_edit.",
             _obj({"command": s, "timeout_seconds": i}, ["command"]), run_command, needs_approval=True,
             read_only=False),
        Tool("list_traces", "List trace/log files (newest first) from the trace directories (CODEPILOT_TRACE_DIRS, "
             "or folders named traces/, logs/, results/ ... in the workspace).",
             _obj({"limit": i}), list_traces),
        Tool("trace_outline", "Summarise one JSON/JSONL trace file: record count, trace/session ids, and a "
             "timeline of spans (offset, duration, name, status) with errors flagged. Start here before "
             "reading a trace in full.", _obj({"path": s}, ["path"]), trace_outline),
        Tool("search_traces", "Regex/text search (case-insensitive) across trace and log files. Use it to find a "
             "session/trace id, an error message, a tool name, or a user query.",
             _obj({"query": s, "max_results": i}, ["query"]), search_traces),
        Tool("read_trace", "Read a trace/log file by path (workspace-relative, trace-dir-relative, or absolute "
             "within a trace dir), with line numbers.",
             _obj({"path": s, "start_line": i, "end_line": i}, ["path"]), read_trace),
        Tool("write_scratch", "Write a throwaway file outside the workspace (a repro script, test harness, or "
             "fixture) without touching the user's code. Returns its absolute path; run it with run_command. "
             "Use it to build a fast, deterministic reproduction before fixing a bug.",
             _obj({"name": {**s, "description": "File name, e.g. repro_price_filter.py"}, "content": s},
                  ["name", "content"]), write_scratch, read_only=False),
        Tool("propose_edit", "Propose a change to one file by exact string replacement. `old_text` must appear "
             "exactly once in the current file on disk; to create a new file pass old_text as ''. Nothing is "
             "written until the user approves. Combine nearby changes into one edit.",
             _obj({"path": s, "old_text": s, "new_text": s,
                   "reason": {**s, "description": "One line: why this change"}},
                  ["path", "old_text", "new_text"]), propose_edit, read_only=False),
        Tool("update_plan", "Show the user a checklist for multi-step work and keep it current: send the full "
             "list each time with each item's status (todo, doing, done).",
             _obj({"items": {"type": "array", "items": _obj({"text": s, "status": {
                 "type": "string", "enum": ["todo", "doing", "done"]}}, ["text", "status"])}}, ["items"]),
             update_plan, needs_workspace=False, read_only=False),
        Tool("load_skill", "Load the full instructions of a skill listed in the system prompt before doing that "
             "kind of task.", _obj({"name": s}, ["name"]), load_skill, needs_workspace=False),
        Tool("recall", "Search the full original conversation that compaction summarised away (BM25 keyword "
             "search, exact text back). Use it when you need a detail the Memory summary lacks: the user's exact "
             "words, a value, an error message, a tool result. scope 'workspace' also searches earlier sessions on "
             "this folder.",
             _obj({"query": {**s, "description": "Keywords, e.g. 'rounding half_up invoice total'"},
                   "scope": {"type": "string", "enum": ["session", "workspace"]}, "limit": i}, ["query"]),
             recall, needs_workspace=False),
        Tool("write_spec", "Write a document of the active spec (spec mode): requirements, design or tasks. Writes "
             "the whole file; no approval needed. The user reviews and approves each phase in the Spec tab.",
             _obj({"doc": {"type": "string", "enum": ["requirements", "design", "tasks"]}, "content": s},
                  ["doc", "content"]), write_spec, read_only=False),
        Tool("update_task", "Mark a task of the active spec todo, in_progress or done (implementation phase), by its "
             "number, e.g. '2.1'.", _obj({"task": s, "status": {"type": "string",
                                                                 "enum": ["todo", "in_progress", "done"]}},
                                         ["task", "status"]), update_task, read_only=False),
        Tool("view_image", "Look at an image: a screenshot, diagram or chart in the workspace (path) or on the web "
             "(http/https URL). PNG, JPEG, GIF or WebP, up to 3.75 MB.", _obj({"source": s}, ["source"]), view_image),
        Tool("remember", "Save a durable fact about this workspace for future sessions (how to run things, where "
             "key code lives, recurring pitfalls). One line. Never store secrets.",
             _obj({"note": s}, ["note"]), remember, read_only=False),
    ]
    if cfg.web_tools:
        tools.append(Tool(
            "library_docs", "Current documentation and code examples for a library, framework or SDK (from Context7), "
            "e.g. library='fastapi', question='how to add a dependency with a database session'. Use it "
            "instead of guessing at APIs. Only the library name and question leave the machine: never put secrets "
            "or proprietary code in them.",
            _obj({"library": s, "question": s}, ["library", "question"]), library_docs, needs_workspace=False))
        tools.append(Tool(
            "web_fetch", "Read a web page as text (docs, an issue, a changelog), or an image by URL. The user approves "
            "each site. Don't put secrets or code from the workspace in URLs.",
            _obj({"url": s}, ["url"]), web_fetch, needs_approval=True, needs_workspace=False))
        if cfg.brave_api_key:
            tools.append(Tool(
                "web_search", "Search the web (Brave Search): titles, URLs and snippets. Read a result with web_fetch. "
                "Don't put secrets or proprietary code in queries.",
                _obj({"query": s}, ["query"]), web_search, needs_workspace=False))
    if cfg.github and github.available():
        tools.append(Tool(
            "github", "GitHub via the gh CLI, using the user's existing gh login, for the repo in the workspace (or "
            "any repo with -R owner/name). Read freely: 'pr list', 'pr view 12 --comments', 'pr diff 12', "
            "'pr checks 12', 'issue view 34', 'run list --limit 5', 'run view <id> --log-failed', "
            "'search code \"symbol\" -R org/repo', 'api repos/{owner}/{repo}/pulls/12/comments'. Prefer --json fields "
            "for compact output. Writes (pr create/comment/review, issue create/comment, run rerun, api writes) "
            "need the user's approval; draft the text carefully.",
            _obj({"args": {**s, "description": "Arguments after 'gh', e.g. 'pr view 12 --json title,body,files'"}},
                 ["args"]), github_cli, needs_workspace=False,
            approval_fn=lambda inp: github.classify(shlex.split(str(inp.get("args", "")).removeprefix("gh ")))
            == "write"))
    if cfg.log_groups:
        tools.append(Tool(
            "cloudwatch_logs", "Search CloudWatch Logs (read-only). Allowed groups: " + ", ".join(cfg.log_groups)
            + ". filter_pattern uses CloudWatch filter syntax, e.g. '\"session-123\"' or '{ $.level = \"ERROR\" }'.",
            _obj({"log_group": s, "filter_pattern": s, "hours": n, "limit": i}, ["log_group"]), cloudwatch_logs,
            needs_workspace=False))
    return tools


def _coerce(props: dict, tool_input: dict) -> dict:
    """Smaller models often send numbers as strings; convert to the schema's scalar types."""
    out = dict(tool_input)
    for key, value in tool_input.items():
        kind = props.get(key, {}).get("type")
        if value is None:
            out.pop(key)
        elif kind == "integer" and not isinstance(value, int):
            out[key] = int(float(value))
        elif kind == "number" and not isinstance(value, (int, float)):
            out[key] = float(value)
        elif kind == "string" and not isinstance(value, str):
            out[key] = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        elif kind in ("array", "object") and isinstance(value, str):
            try:
                out[key] = json.loads(value)
            except json.JSONDecodeError:
                if kind == "object":
                    raise ValueError(f"{key} must be a JSON object") from None
                out[key] = [line.strip() for line in value.splitlines() if line.strip()]
            expected = list if kind == "array" else dict
            if not isinstance(out[key], expected):
                raise ValueError(f"{key} must be a JSON {kind}")
    return out


def execute(tool: Tool, ctx: ToolContext, tool_input: dict) -> tuple[str, bool]:
    """Run a tool; returns (output, is_error)."""
    if tool.needs_workspace and ctx.root is None:
        return ("No workspace is open. Ask the user which directory to work in (or use the path they gave) "
                "and call open_workspace."), True
    missing = [k for k in tool.schema.get("required", []) if k not in tool_input]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}", True
    unknown = set(tool_input) - set(tool.schema["properties"])
    if unknown:
        return f"unknown argument(s): {', '.join(sorted(unknown))}", True
    try:
        tool_input = _coerce(tool.schema["properties"], tool_input)
    except ValueError as exc:
        return f"bad argument: {exc}", True
    try:
        return tool.fn(ctx, **tool_input), False
    except ToolError as exc:
        return str(exc), True
    except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
        return f"{type(exc).__name__}: {exc}", True
