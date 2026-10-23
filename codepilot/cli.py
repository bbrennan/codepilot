"""Command line: `codepilot serve | doctor | chat`."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

from .config import Config, load_env_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codepilot", description=__doc__)
    parser.add_argument("--env-file", help="Path to a .env file (default: ./.env)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Run the web UI")
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)
    p_serve.add_argument("--no-browser", action="store_true")

    p_start = sub.add_parser("start", help="Run the web UI in the background and open it (no terminal needed)")
    p_start.add_argument("--port", type=int)
    p_start.add_argument("--no-browser", action="store_true")
    p_start.add_argument("--browser-tab", action="store_true", help="Open a normal browser tab, not an app window")
    sub.add_parser("stop", help="Stop the background server")
    sub.add_parser("status", help="Is the background server running?")
    p_logs = sub.add_parser("logs", help="Show the background server's log")
    p_logs.add_argument("-n", "--lines", type=int, default=60)
    p_logs.add_argument("-f", "--follow", action="store_true")
    sub.add_parser("app", help="Install ~/Applications/Codepilot.app, a double-click launcher (macOS)")

    p_doc = sub.add_parser("doctor", help="Check AWS/Bedrock (or Ollama), models, and the target repo")
    p_doc.add_argument("--repo", help="Target repo (default: CODEPILOT_REPO)")
    p_doc.add_argument("--skip-models", action="store_true", help="Don't call the models")

    p_models = sub.add_parser("models", help="List the models this account can use (and tier fallbacks)")
    p_models.add_argument("--refresh", action="store_true", help="Probe again instead of using the 12h cache")

    p_chat = sub.add_parser("chat", help="Terminal chat (no browser)")
    p_chat.add_argument("--repo", help="Target repo (default: CODEPILOT_REPO)")
    p_chat.add_argument("--tier", choices=["fast", "main", "hard"])
    p_chat.add_argument("--session", help="Resume a session id")

    p_bench = sub.add_parser("bench", help="Benchmark on planted-bug tasks graded by hidden tests")
    bsub = p_bench.add_subparsers(dest="bench_cmd", required=True)
    b_run = bsub.add_parser("run", help="Run tasks headless and grade them")
    b_run.add_argument("--tasks", help="Comma-separated task ids (default: all)")
    b_run.add_argument("--tier", choices=["fast", "main", "hard"], default="main")
    b_run.add_argument("--mode", help="Force a mode for every task (default: each task's own, e.g. debug)")
    b_run.add_argument("--repeat", type=int, default=1, help="Runs per task, to measure variance")
    b_run.add_argument("--jobs", type=int, default=1, help="Tasks in parallel")
    b_run.add_argument("--max-steps", type=int, default=30)
    b_run.add_argument("--timeout", type=int, default=900, help="Seconds per task before stopping the agent")
    b_run.add_argument("--label", default="", help="Name for this run (shown in reports and compare)")
    b_run.add_argument("--out", default="bench/results")
    b_run.add_argument("--prices", help="TOML of per-1M-token prices for cost estimates (bench/prices.example.toml)")
    b_run.add_argument("--keep", action="store_true", help="Keep each task's working folder for inspection")
    bsub.add_parser("list", help="List tasks")
    b_val = bsub.add_parser("validate", help="Check tasks fail unfixed and pass with the reference solution")
    b_val.add_argument("--tasks")
    b_cmpx = bsub.add_parser("compaction", help="Score how many key facts survive /compact (uses the summariser model)")
    b_cmpx.add_argument("--repeat", type=int, default=1)
    b_cmpx.add_argument("--model", help="Summariser model to evaluate (default: the fast tier's model)")
    b_cmpx.add_argument("--out", default="bench/results")
    b_run.add_argument("--context-tokens", type=int, help="Pretend the window is this small, to stress compaction")
    b_run.add_argument("--compact-at", type=float, help="Override CODEPILOT_COMPACT_AT for this run")
    b_run.add_argument("--prune-at", type=float, help="Override CODEPILOT_PRUNE_AT for this run")
    b_cmp = bsub.add_parser("compare", help="Compare two results.json files")
    b_cmp.add_argument("a")
    b_cmp.add_argument("b")

    args = parser.parse_args(argv)
    env_path = load_env_file(args.env_file)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not os.environ.get("CODEPILOT_VERBOSE"):
        # Per-request lines ("HTTP Request: POST ...", "Loading cached SSO token") on every model call are noise.
        for name in ("httpx", "httpcore", "botocore", "boto3", "urllib3", "anthropic", "openai"):
            logging.getLogger(name).setLevel(logging.WARNING)
    try:
        cfg = Config.from_env()
    except ValueError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    if args.command == "serve":
        return serve(cfg, args, env_path)
    if args.command in ("start", "stop", "status", "logs", "app"):
        from . import service

        if args.command == "start":
            return service.start(cfg, env_path, args.port, not args.no_browser, not args.browser_tab)
        if args.command == "logs":
            return service.logs(cfg, args.lines, args.follow)
        if args.command == "app":
            return service.install_app(cfg, env_path)
        return getattr(service, args.command)(cfg)
    if args.command == "doctor":
        return doctor(cfg, args, env_path)
    if args.command == "bench":
        return bench_cmd(cfg, args)
    if args.command == "models":
        return print_models(cfg, refresh=args.refresh)
    return chat(cfg, args)


def serve(cfg: Config, args, env_path: Path | None) -> int:
    import uvicorn

    from .server import create_app

    host = args.host or cfg.host
    port = args.port or cfg.port
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}"
    print(f"codepilot: provider={cfg.provider} env={env_path or '(environment only)'}")
    print(f"codepilot: open {url}")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="warning")
    return 0


# -- doctor ---------------------------------------------------------------------------------------

OK, WARN, FAIL = "\033[32mok\033[0m", "\033[33mwarn\033[0m", "\033[31mFAIL\033[0m"


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"  [{status}] {label}" + (f": {detail}" if detail else ""))


def doctor(cfg: Config, args, env_path: Path | None) -> int:
    failures = 0
    print(f"env file: {env_path or '(none found; using the process environment)'}")
    print(f"provider: {cfg.provider}")
    for tier, model in cfg.models.items():
        window = cfg.context_window(model) if model else 0
        print(f"  {tier:>4}: {model}  (context window {window:,} tokens"
              f"{', set by CODEPILOT_CONTEXT_TOKENS' if cfg.context_tokens else ''})")

    if cfg.provider == "bedrock":
        failures += _doctor_bedrock(cfg, args.skip_models)
    elif cfg.provider in ("anthropic", "openai"):
        failures += _doctor_direct(cfg, args.skip_models)
    else:
        failures += _doctor_ollama(cfg, args.skip_models)
    failures += _doctor_github(cfg)

    repo = args.repo or cfg.default_repo
    print("\nworkspace")
    if not repo:
        _line(OK, "none preset", "name a directory in chat or in the UI (CODEPILOT_REPO sets a default)")
    else:
        failures += _doctor_repo(cfg, Path(repo).expanduser().resolve())
    print("\nstate: " + str(cfg.home))
    print("\nall checks passed" if not failures else f"\n{failures} check(s) failed")
    return 1 if failures else 0


def _doctor_bedrock(cfg: Config, skip_models: bool) -> int:
    from .bedrock import explain_error, make_client

    failures = 0
    print("\naws")
    _line(OK if cfg.profile else WARN, "profile", cfg.profile or "not set (default credential chain)")
    _line(OK, "region", cfg.region)
    if cfg.endpoint_url:
        _line(OK, "endpoint", cfg.endpoint_url)
    _line(OK, "TLS", f"CA bundle {cfg.ca_bundle}" if cfg.ca_bundle else
          ("OS trust store (truststore)" if cfg.system_certs else "certifi default bundle"))
    try:
        ident = make_client(cfg, "sts").get_caller_identity()
        _line(OK, "identity", ident["Arn"])
    except Exception as exc:
        _line(FAIL, "identity", explain_error(exc, cfg))
        return failures + 1
    if skip_models:
        return failures
    print("\nmodels (each probed with a tiny request; cached for 12h)")
    from . import models

    data = models.discover(cfg, refresh=True)
    enabled = [m for m in data["models"] if m["available"]]
    for m in data["models"]:
        _line(OK if m["available"] else WARN, m["id"], f"{m['api']}" + ("" if m["available"] else f": {m['reason']}"))
    print("\ntiers")
    for tier, t in data["tiers"].items():
        if t["fallback"]:
            _line(WARN, tier, f"{t['configured']} not enabled for this account; using {t['model']}")
        else:
            ok = any(m["id"] == t["model"] for m in enabled)
            failures += 0 if ok else 1
            _line(OK if ok else FAIL, tier, t["model"])
    return failures


def _doctor_direct(cfg: Config, skip_models: bool) -> int:
    """Anthropic API or OpenAI API with the user's own key."""
    import os

    from .agent import make_llm
    from .bedrock import BedrockError

    key_var = "ANTHROPIC_API_KEY" if cfg.provider == "anthropic" else "OPENAI_API_KEY"
    base = cfg.anthropic_base_url if cfg.provider == "anthropic" else cfg.openai_base_url
    print(f"\n{cfg.provider} api")
    if not os.environ.get(key_var):
        _line(FAIL, key_var, "not set; add it to .env (see docs/setup.md)")
        return 1
    _line(OK, key_var, "set (value hidden)")
    if base:
        _line(OK, "base url", base)
    if cfg.effort:
        _line(OK, "effort", cfg.effort)
    llm = make_llm(cfg)
    failures = 0
    try:
        available = llm.list_models()
        _line(OK, "models visible", str(len(available)))
    except Exception as exc:  # noqa: BLE001 - any SDK/network error is a failed check
        _line(FAIL, "list models", str(exc)[:200])
        return 1
    for tier, model in cfg.models.items():
        if not model:
            failures += 1
            _line(FAIL, tier, "no model set (CODEPILOT_OPENAI_MODEL)")
        elif available and model not in available:
            _line(WARN, tier, f"{model} not in this key's model list")
    if failures or skip_models:
        if failures:
            print("  Models your key can use:\n    " + "\n    ".join(sorted(available)[:60]))
        return failures
    print("\nmodels (one tiny call each)")
    for tier, model in cfg.models.items():
        try:
            reply = llm.complete(model, "Reply with the single word OK.", "ping", max_tokens=64)
            _line(OK, tier, f"{model} -> {reply[:30]!r}")
        except BedrockError as exc:
            failures += 1
            _line(FAIL, tier, str(exc))
    return failures


def _doctor_github(cfg: Config) -> int:
    from . import github

    print("\ngithub")
    if not cfg.github:
        _line(OK, "disabled", "CODEPILOT_GITHUB=0")
        return 0
    st = github.status(cfg.github_host)
    if st.get("available"):
        _line(OK, "gh", f"signed in as {st['user']} @ {st['host']}")
    else:
        _line(WARN, "gh", st.get("reason", "unavailable") + " (optional)")
    return 0


def _doctor_ollama(cfg: Config, skip_models: bool) -> int:
    from .bedrock import BedrockError
    from .ollama import Ollama

    print("\nollama")
    llm = Ollama(cfg)
    try:
        installed = llm.list_models()
        _line(OK, "server", cfg.ollama_url)
    except OSError as exc:
        _line(FAIL, "server", f"{cfg.ollama_url} unreachable ({exc}); run: ollama serve")
        return 1
    failures = 0
    for model in sorted(set(cfg.models.values())):
        if model in installed or f"{model}:latest" in installed:
            _line(OK, "model", model)
        else:
            failures += 1
            _line(FAIL, "model", f"{model} not pulled; run: ollama pull {model}")
    if not failures and not skip_models:
        try:
            reply = llm.complete(cfg.models["main"], "Reply with the single word OK.", "ping", max_tokens=8)
            _line(OK, "generate", repr(reply[:30]))
        except BedrockError as exc:
            failures += 1
            _line(FAIL, "generate", str(exc))
    return failures


def _doctor_repo(cfg: Config, root: Path) -> int:
    from .store import Store
    from .tools import ToolContext, _trace_files, trace_roots

    if not root.is_dir():
        _line(FAIL, "path", f"{root} does not exist")
        return 1
    failures = 0
    _line(OK, "path", str(root))
    _line(OK if (root / ".git").exists() else WARN, "git", "yes" if (root / ".git").exists() else "not a git repo")
    from .tools import detect_test_cmd

    test_cmd = detect_test_cmd(root, cfg)
    if not test_cmd:
        _line(WARN, "test cmd", "none detected; set CODEPILOT_TEST_CMD or tell codepilot in chat")
    for label, cmd in (("test cmd", test_cmd), ("eval cmd", cfg.eval_cmd)):
        if not cmd:
            continue
        exe = cmd.split()[0]
        found = shutil.which(exe)
        _line(OK if found else FAIL, label, f"{cmd}" + ("" if found else f" ({exe} not on PATH)"))
        failures += 0 if found else 1
    if cfg.eval_cmd.startswith("make "):
        target = cfg.eval_cmd.split()[1]
        makefile = root / "Makefile"
        has = makefile.exists() and any(line.startswith(f"{target}:") for line in makefile.read_text().splitlines())
        _line(OK if has else WARN, "make target", target if has else f"{target} not found in {makefile}")
    ctx = ToolContext(root=root, cfg=cfg, store=Store(cfg.home), session_id="doctor")
    roots = trace_roots(ctx)
    files = _trace_files(ctx) if roots else []
    if roots:
        _line(OK, "traces", f"{len(files)} files under " + ", ".join(str(r) for r in roots))
    else:
        _line(WARN, "traces", "no trace dir found; set CODEPILOT_TRACE_DIRS (e.g. traces or an absolute path)")
    return failures


# -- models ---------------------------------------------------------------------------------------


def print_models(cfg: Config, refresh: bool = True) -> int:
    from . import models

    print(f"Checking which models this account can use ({cfg.provider}"
          f"{', ' + cfg.region if cfg.provider == 'bedrock' else ''})…")
    data = models.discover(cfg, refresh=refresh)
    for m in data["models"]:
        status = OK if m["available"] else WARN
        window = f"{m['window'] // 1000}k" if m["window"] < 1_000_000 else f"{m['window'] // 1_000_000}M"
        detail = f"{m['label']} · {m['api']} · {window}" + ("" if m["available"] else f" · {m['reason']}")
        _line(status, m["id"], detail)
    print("\ntiers")
    for tier, t in data["tiers"].items():
        note = f" (configured {t['configured']} is not available, using this instead)" if t["fallback"] else ""
        _line(WARN if t["fallback"] else OK, tier, t["model"] + note)
    return 0 if any(m["available"] for m in data["models"]) else 1


# -- bench ----------------------------------------------------------------------------------------


def bench_cmd(cfg: Config, args) -> int:
    import tomllib

    from . import bench

    ids = [t.strip() for t in (getattr(args, "tasks", None) or "").split(",") if t.strip()] or None
    if args.bench_cmd == "list":
        for t in bench.load_tasks():
            print(f"{t.id:28} {t.category:13} {t.difficulty:7} {t.mode:6} {t.title}")
        return 0
    if args.bench_cmd == "validate":
        return 0 if bench.validate(ids) else 1
    if args.bench_cmd == "compare":
        print(bench.compare(Path(args.a), Path(args.b)))
        return 0
    if args.bench_cmd == "compaction":
        report = bench.compaction_eval(cfg, repeat=args.repeat, model=args.model, out=Path(args.out))
        return 0 if report["recall"] >= 0.9 else 1
    from dataclasses import replace

    overrides = {k: v for k, v in (("context_tokens", args.context_tokens), ("compact_at", args.compact_at),
                                   ("prune_at", args.prune_at)) if v is not None}
    cfg = replace(cfg, **overrides)
    prices = tomllib.loads(Path(args.prices).read_text()) if args.prices else None
    report = bench.run(cfg, ids, tier=args.tier, mode=args.mode, repeat=args.repeat, jobs=args.jobs,
                       max_steps=args.max_steps, timeout=args.timeout, out=Path(args.out), keep=args.keep,
                       label=args.label, prices=prices)
    return 0 if report["summary"]["runs"] else 1


# -- terminal chat --------------------------------------------------------------------------------


def chat(cfg: Config, args) -> int:
    from .agent import Agent
    from .store import Store

    store = Store(cfg.home)
    agent = Agent(cfg, store)
    if args.session:
        sess = store.get_session(args.session)
    else:
        repo = args.repo or cfg.default_repo
        root = str(Path(repo).expanduser().resolve()) if repo else ""
        sess = store.create_session(root, args.tier or cfg.default_tier)
    where = sess.repo or "no workspace yet (name a directory in chat)"
    print(f"session {sess.id} on {where} ({cfg.provider}:{cfg.models[sess.tier]}). Ctrl-D to quit.")
    while True:
        try:
            text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text.startswith(("/apply ", "/reject ")):
            _proposal_command(store, sess, text)
            continue
        events = agent.chat(sess.id, text, args.tier)
        while events is not None:
            events = _render(events, agent, sess.id)


def _proposal_command(store, sess, text: str) -> None:
    from .tools import ToolError, apply_proposal

    verb, _, num = text.partition(" ")
    try:
        prop = store.get_proposal(int(num))
    except (KeyError, ValueError):
        print(f"no proposal {num}")
        return
    if prop.status != "pending":
        print(f"proposal #{prop.id} is already {prop.status}")
        return
    if verb == "/reject":
        store.set_proposal_status(prop.id, "rejected")
        print(f"rejected #{prop.id}")
        return
    try:
        before, after = apply_proposal(Path(sess.repo), prop)
        store.record_applied(prop.id, before, after)
        print(f"applied #{prop.id} to {prop.path}")
    except (ToolError, OSError) as exc:
        store.set_proposal_status(prop.id, "failed")
        print(f"could not apply: {exc}")


def _render(events, agent, sid):
    for ev in events:
        t = ev["type"]
        if t == "text":
            print(ev["text"], end="", flush=True)
        elif t == "tool_call":
            print(f"\n  -> {ev['name']} {json.dumps(ev['input'])[:160]}")
        elif t == "tool_result":
            first = ev["output"].strip().splitlines()[:1]
            print(f"  <- {'ERROR ' if ev['is_error'] else ''}{first[0][:160] if first else ''}")
        elif t == "proposal":
            print(f"\n--- proposal #{ev['proposal']['id']} ---\n{ev['proposal']['diff']}")
        elif t == "plan":
            marks = {"done": "x", "doing": ">"}
            print("\n  plan: " + " | ".join(f"[{marks.get(i['status'], ' ')}] {i['text']}" for i in ev["items"]))
        elif t == "sub_tool":
            print(f"    explore -> {ev['name']} {ev['detail'][:120]}")
        elif t in ("error", "notice"):
            print(f"\n[{t}] {ev['message']}")
        elif t == "approval_needed":
            for tool in ev["tools"]:
                print(f"\n  approve: {tool['command']}")
            answer = input("  run it? [y/N] ").strip().lower() == "y"
            return agent.resume(sid, answer)
    print()
    return None


if __name__ == "__main__":
    sys.exit(main())
