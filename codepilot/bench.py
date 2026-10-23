"""Benchmark: run codepilot headless on planted-bug tasks and grade the result with hidden tests.

Each task lives in bench/tasks/<id>/ with:
  task.toml   id, title, category, difficulty, mode, prompt, test_cmd, grade_cmd
  repo/       the project the agent works on (copied to a temp dir per run)
  hidden/     tests the agent never sees, copied in only for grading
  solution/   a reference fix (overlay of repo/ files) used by `codepilot bench validate`

A run copies repo/ to a scratch folder, commits it, gives the agent the prompt in the task's mode with
edits auto-applied and only safe commands approved, then copies hidden/ in and runs grade_cmd. Pass/fail is
decided by the hidden tests alone.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .agent import Agent, make_llm
from .config import Config
from .store import Store

TASKS_DIR = Path(__file__).resolve().parent.parent / "bench" / "tasks"
SAFE_COMMANDS = {"python", "python3", "pytest", "uv", "ls", "cat", "head", "tail", "grep", "rg", "find", "wc",
                 "diff", "echo", "sort", "pwd", "tree", "git"}
SAFE_GIT = {"status", "diff", "log", "show", "blame", "bisect", "rev-parse", "ls-files"}
FORBIDDEN_SHELL = (";", "&&", "||", "`", "$(", ">", "<", "\n")


@dataclass
class Task:
    id: str
    title: str
    category: str
    difficulty: str
    mode: str
    prompt: str
    test_cmd: str
    grade_cmd: str
    path: Path


def load_tasks(only: list[str] | None = None, tasks_dir: Path = TASKS_DIR) -> list[Task]:
    tasks = []
    for d in sorted(p for p in tasks_dir.iterdir() if (p / "task.toml").is_file()):
        meta = tomllib.loads((d / "task.toml").read_text())
        if only and meta["id"] not in only:
            continue
        tasks.append(Task(id=meta["id"], title=meta["title"], category=meta.get("category", ""),
                          difficulty=meta.get("difficulty", ""), mode=meta.get("mode", "debug"),
                          prompt=meta["prompt"].strip(), test_cmd=meta.get("test_cmd", "python3 -m pytest -q"),
                          grade_cmd=meta.get("grade_cmd", "python -m pytest -q"), path=d))
    if only:
        missing = set(only) - {t.id for t in tasks}
        if missing:
            raise SystemExit(f"unknown task(s): {', '.join(sorted(missing))}")
    return tasks


# -- approvals ------------------------------------------------------------------------------------


def command_is_safe(command: str) -> bool:
    """Allow simple read/test commands; pipes are fine if every stage is on the allowlist."""
    if any(tok in command for tok in FORBIDDEN_SHELL):
        return False
    for stage in command.split("|"):
        try:
            argv = shlex.split(stage)
        except ValueError:
            return False
        if not argv or Path(argv[0]).name not in SAFE_COMMANDS:
            return False
        if Path(argv[0]).name == "git" and (len(argv) < 2 or argv[1] not in SAFE_GIT):
            return False
    return True


def approve(tools: list[dict]) -> bool:
    for t in tools:
        if t["name"] in ("run_tests", "run_checks"):
            continue
        if t["name"] == "run_command" and command_is_safe(str(t["input"].get("command", ""))):
            continue
        return False
    return True


# -- running --------------------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@example.com",
           "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@example.com"}
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env, check=False)
    return proc.stdout


def prepare(task: Task, work: Path) -> Path:
    repo = work / "repo"
    shutil.copytree(task.path / "repo", repo)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "baseline")
    return repo


def grade(task: Task, repo: Path, timeout: int = 300) -> tuple[bool, str]:
    shutil.copytree(task.path / "hidden", repo, dirs_exist_ok=True)
    argv = shlex.split(task.grade_cmd)
    if argv and argv[0] in ("python", "python3"):
        argv[0] = sys.executable
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    try:
        proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    except subprocess.TimeoutExpired:
        return False, f"grading timed out after {timeout}s"
    out = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, "\n".join(out.splitlines()[-30:])


def run_task(task: Task, base_cfg: Config, llm_factory: Callable[[Config], Any], tier: str, mode: str | None,
             out_dir: Path, max_steps: int, timeout: int, keep: bool, run_index: int = 0) -> dict:
    work = Path(tempfile.mkdtemp(prefix=f"cpbench-{task.id}-"))
    repo = prepare(task, work)
    cfg = replace(base_cfg, home=work / "home", test_cmd=task.test_cmd, auto_apply_edits=True,
                  auto_approve_tests=True, github=False, max_steps=max_steps, trace_dirs=[], log_groups=[],
                  default_repo=None)
    store = Store(cfg.home)
    agent = Agent(cfg, store, llm=llm_factory(cfg))
    sess = store.create_session(str(repo), tier)
    store.update_session(sess.id, mode=mode or task.mode)

    events: list[dict] = []
    tools: dict[str, int] = {}
    denied = 0
    started = time.monotonic()
    timed_out = False
    gen = agent.chat(sess.id, task.prompt)
    while gen is not None:
        nxt = None
        for ev in gen:
            events.append(ev)
            if ev["type"] == "tool_call":
                tools[ev["name"]] = tools.get(ev["name"], 0) + 1
            if time.monotonic() - started > timeout and not timed_out:
                timed_out = True
                agent.cancel(sess.id)
            if ev["type"] == "approval_needed":
                ok = approve(ev["tools"])
                denied += 0 if ok else 1
                nxt = agent.resume(sess.id, ok)
                break
        gen = nxt
    elapsed = time.monotonic() - started

    passed, grade_out = grade(task, repo)
    usage = store.usage(sess.id)["by_model"]
    noise = ("tests_hidden", "__pycache__", ".pytest_cache")
    changed = [ln for ln in _git(repo, "status", "--porcelain").splitlines() if not any(n in ln for n in noise)]
    answer = "".join(e.get("text", "") for e in events if e["type"] == "text")[-4000:]
    errors = [e["message"] for e in events if e["type"] == "error"]

    stem = f"{task.id}" + (f"-r{run_index}" if run_index else "")
    (out_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    with (out_dir / "transcripts" / f"{stem}.jsonl").open("w") as fh:
        for ev in events:
            fh.write(json.dumps(ev, default=str) + "\n")
    diff = _git(repo, "diff", "HEAD", "--", ".", ":(exclude)tests_hidden")
    (out_dir / "transcripts" / f"{stem}.diff").write_text(diff)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)

    return {
        "task": task.id, "title": task.title, "category": task.category, "difficulty": task.difficulty,
        "mode": mode or task.mode, "run": run_index, "passed": passed, "seconds": round(elapsed, 1),
        "timed_out": timed_out, "model_calls": sum(u["calls"] for u in usage),
        "input_tokens": sum(u["input"] or 0 for u in usage), "output_tokens": sum(u["output"] or 0 for u in usage),
        "cache_read_tokens": sum(u["cache_read"] or 0 for u in usage),
        "cache_write_tokens": sum(u["cache_write"] or 0 for u in usage),
        "tool_calls": tools, "approvals_denied": denied, "files_changed": changed,
        "errors": errors[:5], "grade_output": grade_out, "answer_tail": answer[-1500:],
        "workdir": str(work) if keep else None,
    }


def run(cfg: Config, task_ids: list[str] | None = None, tier: str = "main", mode: str | None = None,
        repeat: int = 1, jobs: int = 1, max_steps: int = 30, timeout: int = 900, out: Path | None = None,
        keep: bool = False, label: str = "", prices: dict | None = None,
        llm_factory: Callable[[Config], Any] = make_llm, progress: Callable[[str], None] = print) -> dict:
    tasks = load_tasks(task_ids)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = (out or Path("bench/results")) / f"{stamp}{'-' + label if label else ''}"
    out_dir.mkdir(parents=True, exist_ok=True)
    model = cfg.models[tier]
    progress(f"bench: {len(tasks)} task(s) x {repeat} on {cfg.provider}:{model} (tier {tier}"
             f"{', mode ' + mode if mode else ''}) -> {out_dir}")
    jobs_list = [(t, r) for r in range(repeat) for t in tasks]

    def one(item):
        task, r = item
        try:
            res = run_task(task, cfg, llm_factory, tier, mode, out_dir, max_steps, timeout, keep, r)
        except Exception as exc:  # a crash in one task shouldn't lose the whole run
            res = {"task": task.id, "title": task.title, "category": task.category, "difficulty": task.difficulty,
                   "mode": mode or task.mode, "run": r, "passed": False, "seconds": 0, "errors": [repr(exc)],
                   "model_calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                   "cache_write_tokens": 0, "tool_calls": {}, "files_changed": [], "grade_output": ""}
        progress(f"  {'PASS' if res['passed'] else 'FAIL'}  {task.id}{f' (run {r})' if repeat > 1 else ''}"
                 f"  {res['seconds']}s  {res['model_calls']} calls")
        return res

    if jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(one, jobs_list))
    else:
        results = [one(item) for item in jobs_list]

    report = {
        "label": label, "started": stamp, "provider": cfg.provider, "model": model, "tier": tier,
        "mode": mode or "per-task", "repeat": repeat, "max_steps": max_steps, "results": results,
        "summary": summarize(results, model, prices),
    }
    (out_dir / "results.json").write_text(json.dumps(report, indent=2))
    (out_dir / "report.md").write_text(markdown(report))
    progress(f"bench: {report['summary']['passed']}/{report['summary']['runs']} passed "
             f"({report['summary']['pass_rate']:.0%}). Report: {out_dir / 'report.md'}")
    return report


def summarize(results: list[dict], model: str, prices: dict | None) -> dict:
    n = len(results)
    passed = sum(r["passed"] for r in results)
    tot = {k: sum(r.get(k, 0) or 0 for r in results)
           for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "seconds",
                     "model_calls")}
    summary = {"runs": n, "passed": passed, "pass_rate": passed / n if n else 0.0, **tot,
               "by_category": {}}
    for r in results:
        c = summary["by_category"].setdefault(r["category"], {"runs": 0, "passed": 0})
        c["runs"] += 1
        c["passed"] += int(r["passed"])
    price = _price_for(model, prices)
    if price:
        cost = (tot["input_tokens"] * price.get("input", 0) + tot["output_tokens"] * price.get("output", 0)
                + tot["cache_read_tokens"] * price.get("cache_read", 0)
                + tot["cache_write_tokens"] * price.get("cache_write", 0)) / 1e6
        summary["cost_usd"] = round(cost, 4)
        summary["cost_per_pass_usd"] = round(cost / passed, 4) if passed else None
    return summary


def _price_for(model: str, prices: dict | None) -> dict | None:
    if not prices:
        return None
    for key, value in prices.items():
        if key in model:
            return value
    return None


def markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"# codepilot benchmark{' - ' + report['label'] if report['label'] else ''}",
        "",
        f"- **When:** {report['started']}  ",
        f"- **Model:** `{report['provider']}:{report['model']}` (tier `{report['tier']}`), mode: {report['mode']}  ",
        f"- **Result:** **{s['passed']}/{s['runs']} passed ({s['pass_rate']:.0%})**  ",
        f"- **Tokens:** {s['input_tokens']:,} in / {s['output_tokens']:,} out "
        f"({s['cache_read_tokens']:,} cache reads), {s['model_calls']} model calls, {s['seconds']:.0f}s total",
    ]
    if "cost_usd" in s:
        lines.append(f"- **Estimated cost:** ${s['cost_usd']:.4f}"
                     + (f" (${s['cost_per_pass_usd']:.4f} per passing task)" if s.get("cost_per_pass_usd") else ""))
    lines += ["", "| Category | Passed |", "|---|---|"]
    lines += [f"| {c} | {v['passed']}/{v['runs']} |" for c, v in sorted(s["by_category"].items())]
    lines += ["", "| Task | Category | Mode | Result | Time | Calls | Tokens in/out | Tools |",
              "|---|---|---|---|---|---|---|---|"]
    for r in report["results"]:
        tools = ", ".join(f"{k}x{v}" for k, v in sorted((r.get("tool_calls") or {}).items()))
        lines.append(f"| {r['task']}{' #' + str(r['run']) if report['repeat'] > 1 else ''} | {r['category']} | "
                     f"{r['mode']} | {'PASS' if r['passed'] else 'FAIL'} | {r['seconds']}s | {r['model_calls']} | "
                     f"{r['input_tokens']:,}/{r['output_tokens']:,} | {tools} |")
    fails = [r for r in report["results"] if not r["passed"]]
    if fails:
        lines += ["", "## Failures", ""]
        for r in fails:
            lines += [f"### {r['task']}", "", f"Files changed: {', '.join(r.get('files_changed') or []) or 'none'}"]
            if r.get("errors"):
                lines.append(f"Errors: {'; '.join(r['errors'])}")
            lines += ["", "```", (r.get("grade_output") or "")[-2000:], "```", ""]
    return "\n".join(lines) + "\n"


def compare(a_path: Path, b_path: Path) -> str:
    a, b = (json.loads(Path(p).read_text()) for p in (a_path, b_path))

    def by_task(rep):
        out: dict[str, list[bool]] = {}
        for r in rep["results"]:
            out.setdefault(r["task"], []).append(r["passed"])
        return out

    ta, tb = by_task(a), by_task(b)
    name = lambda rep: rep.get("label") or f"{rep['model']} ({rep['mode']})"  # noqa: E731
    lines = [f"A: {name(a)}  {a['summary']['passed']}/{a['summary']['runs']}  "
             f"tokens {a['summary']['input_tokens'] + a['summary']['output_tokens']:,}  {a['summary']['seconds']:.0f}s",
             f"B: {name(b)}  {b['summary']['passed']}/{b['summary']['runs']}  "
             f"tokens {b['summary']['input_tokens'] + b['summary']['output_tokens']:,}  {b['summary']['seconds']:.0f}s",
             "", f"{'task':32} {'A':>6} {'B':>6}"]
    for task in sorted(set(ta) | set(tb)):
        fmt = lambda v: f"{sum(v)}/{len(v)}" if v else "-"  # noqa: E731
        ra, rb = ta.get(task, []), tb.get(task, [])
        flag = "  <- B better" if rb and ra and sum(rb) / len(rb) > sum(ra) / len(ra) else \
               "  <- A better" if rb and ra and sum(ra) / len(ra) > sum(rb) / len(rb) else ""
        lines.append(f"{task:32} {fmt(ra):>6} {fmt(rb):>6}{flag}")
    return "\n".join(lines)


def validate(task_ids: list[str] | None = None, progress: Callable[[str], None] = print) -> bool:
    """Check every task discriminates: hidden tests fail on repo/ and pass with solution/ applied."""
    ok = True
    for task in load_tasks(task_ids):
        with tempfile.TemporaryDirectory(prefix=f"cpvalidate-{task.id}-") as tmp:
            repo = prepare(task, Path(tmp))
            before, _ = grade(task, repo)
            shutil.copytree(task.path / "solution" / "repo", repo, dirs_exist_ok=True)
            after, out = grade(task, repo)
        good = (not before) and after
        ok &= good
        progress(f"  {'ok  ' if good else 'BAD '} {task.id}: unfixed={'fail' if not before else 'PASS?!'}, "
                 f"solution={'pass' if after else 'FAIL'}" + ("" if after else f"\n{out}"))
    return ok
