"""Verification receipts: test pending changes before the user reviews them.

Proposed edits aren't on disk until applied, so a test run during a turn tests the old code. Instead, the
workspace is cloned (copy-on-write where the filesystem can), the pending changes are applied to the clone, and the
test command and analysers run there. The workspace itself is only ever read.

A cloned virtualenv still runs the workspace's code: its scripts' shebangs and its editable installs name the
workspace path. relocate_envs rewrites those to the copy, and reports anything it couldn't, so a receipt never
claims to have tested the changes when it may have tested the original.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import checks
from .config import Config
from .store import Proposal
from .tools import ToolError, apply_proposal, detect_test_cmd

OUTPUT_TAIL = 6000


def fingerprint(proposals: list[Proposal]) -> str:
    """Identifies a pending set: any change to it (new, gone, a new version) gives a different value."""
    parts = [(p.id, p.path, p.old_text, p.new_text) for p in sorted(proposals, key=lambda p: p.id)]
    return hashlib.sha1(json.dumps(parts).encode()).hexdigest()


def clone_tree(src: Path, dst: Path) -> None:
    """Copy src to dst (which must not exist), copy-on-write where the filesystem supports it."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fast = ["cp", "-c", "-R"] if sys.platform == "darwin" else ["cp", "-a", "--reflink=auto"]
    if subprocess.run([*fast, str(src), str(dst)], capture_output=True, check=False).returncode == 0:
        return
    shutil.rmtree(dst, ignore_errors=True)  # a partial copy from the failed fast path
    shutil.copytree(src, dst, symlinks=True)


def _env_files(venv: Path) -> list[Path]:
    """The files of a virtualenv that can name its project's path: scripts, and how installs point at code."""
    files = [p for d in ("bin", "Scripts") if (venv / d).is_dir()
             for p in (venv / d).iterdir() if p.is_file() and not p.is_symlink()]
    for site in [*venv.glob("lib/python*/site-packages"), venv / "Lib/site-packages"]:
        if site.is_dir():
            files += [p for p in site.iterdir() if p.is_file() and p.suffix in (".pth", ".py")]
            files += list(site.glob("*.dist-info/direct_url.json"))
    return files


def relocate_envs(src: Path, dst: Path) -> list[str]:
    """Point virtualenvs copied into dst at dst instead of src. Returns the files (relative to dst) that still
    name src, so the caller can say the copy may run the workspace's code."""
    old = {str(src).encode(), str(src.resolve()).encode()}
    new = str(dst).encode()
    stuck = []
    for cfg in [*dst.glob("*/pyvenv.cfg"), *dst.glob("*/*/pyvenv.cfg")]:
        for path in _env_files(cfg.parent):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if b"\0" in data[:1024] or not any(o in data for o in old):
                continue  # binaries and files that don't mention the workspace are left alone
            fixed = data
            for o in sorted(old, key=len, reverse=True):
                fixed = fixed.replace(o, new)
            try:
                path.write_bytes(fixed)
            except OSError:
                stuck.append(str(path.relative_to(dst)))
    return sorted(stuck)


@dataclass
class Copy:
    path: Path
    originals: dict[str, str | None] = field(default_factory=dict)  # changed files before the changes (None: new)
    conflict: str = ""  # a change that couldn't be applied after the ones before it
    isolation: list[str] = field(default_factory=list)  # files that may still run the workspace's code


@contextmanager
def prepared(root: Path, proposals: list[Proposal], workdir: Path, copier=clone_tree) -> Iterator[Copy]:
    """A disposable copy of the workspace with these pending changes applied in order; removed afterwards."""
    path = workdir.resolve() / uuid.uuid4().hex[:12]
    try:
        copier(root, path)
        copy = Copy(path, isolation=relocate_envs(root, path))
        for n, p in enumerate(sorted(proposals, key=lambda p: p.id)):
            if p.path not in copy.originals:
                target = path / p.path
                copy.originals[p.path] = target.read_text(errors="replace") if target.is_file() else None
            try:
                apply_proposal(path, p)
            except (ToolError, OSError):
                after = "after the earlier changes" if n else "to the current file"
                copy.conflict = f"#{p.id} ({p.path}) no longer applies {after}"
                break
        yield copy
    finally:
        shutil.rmtree(path, ignore_errors=True)


# -- running the checks on the copy ---------------------------------------------------------------------------------


@dataclass
class Run:
    name: str  # "tests" or an analyser
    kind: str  # tests | lint | types | security
    argv: str
    exit: int | None  # None: timed out
    output: str  # the tail
    baseline_exit: int | None = None  # the same command without the changes; only run when this one failed


@dataclass
class Receipt:
    proposal_ids: list[int]
    fingerprint: str
    status: str = "pass"  # pass | fail | preexisting | unverified | nothing | error | timeout | cancelled
    runs: list[Run] = field(default_factory=list)
    newly_failing: list[str] = field(default_factory=list)  # "tests: <id>", "ruff: <path>: <message>"
    conflict: str = ""
    isolation: list[str] = field(default_factory=list)  # files that may still run the workspace's code
    seconds: float = 0.0


def run_argv(argv: list[str], cwd: Path, timeout: float) -> tuple[int | None, str]:
    """Run a command in the copy, as run_tests would in the workspace. (exit, output tail); exit None: timed out."""
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=max(1.0, timeout), env=env,
                              errors="replace", check=False)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout:.0f}s"
    except OSError as exc:
        return 127, str(exc)
    out = proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr.strip() else "")
    return proc.returncode, out[-OUTPUT_TAIL:]


TEST_IDS = (re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M),  # pytest
            re.compile(r"^\s*✕ (.+?)(?:\s+\(\d+(?:\.\d+)?\s*m?s\))?\s*$", re.M),  # Jest
            re.compile(r"^--- FAIL: (\S+)", re.M))  # go test
FINDING = re.compile(r"^(\S+?):\d+(?::\d+)?:\s*(.+?)\s*$", re.M)  # path:line[:col]: message


def _failures(name: str, output: str) -> set[str]:
    if name == "tests":
        return {m for rx in TEST_IDS for m in rx.findall(output)}
    return {f"{path}: {msg}" for path, msg in FINDING.findall(output)}  # line numbers move when code is edited


def newly_failing(name: str, after: str, after_exit: int, before: str, before_exit: int) -> list[str]:
    """What fails with the changes but not without them."""
    now, then = _failures(name, after), _failures(name, before)
    if now:
        return [f"{name}: {f}" for f in sorted(now - then)]
    return [f"{name}: exit {after_exit} (was 0 without the changes)"] if before_exit == 0 else []


def verify(root: Path, cfg: Config, proposals: list[Proposal], *, workdir: Path, copier=clone_tree,
           runner=run_argv, cancelled=lambda: False, timeout: float = 600, analysers: bool = True,
           clock=time.monotonic) -> Receipt:
    """Apply the pending changes to a copy of the workspace and run its tests and analysers there."""
    started = clock()
    receipt = Receipt(sorted(p.id for p in proposals), fingerprint(proposals))
    with prepared(root, proposals, workdir, copier) as copy:
        receipt.isolation = copy.isolation
        if copy.conflict:
            receipt.status, receipt.conflict = "error", copy.conflict
        else:
            _run_all(copy, cfg, receipt, runner, cancelled, started + timeout, analysers, clock)
    if receipt.status == "pass" and receipt.isolation:
        receipt.status = "unverified"
    receipt.seconds = round(clock() - started, 1)
    return receipt


def _run_all(copy: Copy, cfg: Config, receipt: Receipt, runner, cancelled, deadline: float, analysers: bool,
             clock) -> None:
    commands: list[tuple[str, str, list[str]]] = []
    if test := detect_test_cmd(copy.path, cfg):
        commands.append(("tests", "tests", shlex.split(test)))
    changed = [p for p in copy.originals if (copy.path / p).exists()]
    if analysers and changed:
        commands += [(c.name, c.kind, c.argv) for c in checks.detect(copy.path, changed)]
    if not commands:
        receipt.status = "nothing"
        return
    argvs = {}
    for name, kind, argv in commands:
        if receipt.status != "pass":
            break
        if cancelled():
            receipt.status = "cancelled"
        elif clock() >= deadline:
            receipt.status = "timeout"
        else:
            code, out = runner(argv, copy.path, deadline - clock())
            receipt.runs.append(Run(name, kind, shlex.join(argv), code, out))
            argvs[name] = argv
            if code is None:
                receipt.status = "timeout"
    failed = [r for r in receipt.runs if r.exit not in (0, None)]
    if not failed or receipt.status != "pass":
        return
    for rel, text in copy.originals.items():  # the baseline: the copy as it was, without the changes
        target = copy.path / rel
        if text is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(text)
    for run in failed:
        if cancelled() or clock() >= deadline:
            receipt.status = "cancelled" if cancelled() else "timeout"
            return
        code, out = runner(argvs[run.name], copy.path, deadline - clock())
        run.baseline_exit = code
        receipt.newly_failing += newly_failing(run.name, run.output, run.exit, out, code if code is not None else -1)
    receipt.status = "fail" if receipt.newly_failing else "preexisting"


# -- for the agent: verify a session's pending changes, and say what came of it ---------------------------------


def pending_of(store, sid: str) -> list[Proposal]:
    return [p for p in store.list_proposals(sid) if p.status == "pending"]


def current_fingerprint(store, sid: str) -> str | None:
    pending = pending_of(store, sid)
    return fingerprint(pending) if pending else None


def verify_session(store, cfg: Config, sid: str, root: Path | None, cancelled=lambda: False) -> dict | None:
    """Verify the session's pending changes and store the receipt. None when nothing is pending."""
    pending = pending_of(store, sid)
    if not pending or root is None:
        return None
    receipt = asdict(verify(root, cfg, pending, workdir=cfg.home / "verify" / sid, cancelled=cancelled,
                            timeout=cfg.verify_timeout))
    return {**receipt, "id": store.add_receipt(sid, receipt), "told": False}


STATUS_TEXT = {
    "pass": "pass", "fail": "newly failing", "preexisting": "no new failures (some fail without the changes too)",
    "unverified": "passed, but the copy may have run the workspace's code instead of the changes",
    "nothing": "nothing to run (no test command or analysers found; set CODEPILOT_TEST_CMD)",
    "error": "couldn't apply the changes together", "timeout": "timed out", "cancelled": "cancelled",
}


def describe(receipt: dict, lead: str = "") -> str:
    """The receipt as text for the model."""
    ids = receipt["proposal_ids"]
    lead = lead or ("Verified pending change" + ("s" if len(ids) > 1 else ""))
    lines = [f"{lead} {', '.join(f'#{i}' for i in ids)}: {STATUS_TEXT.get(receipt['status'], receipt['status'])}"
             f" ({receipt['seconds']}s, on a copy of the workspace; nothing was applied)."]
    if receipt["conflict"]:
        lines.append(receipt["conflict"] + ".")
    for run in receipt["runs"]:
        was = "" if run["baseline_exit"] is None else f"; without the changes: exit {run['baseline_exit']}"
        lines.append(f"- {run['name']} (`{run['argv']}`): " + ("timed out" if run["exit"] is None
                                                             else f"exit {run['exit']}") + was)
    if receipt["newly_failing"]:
        lines.append("Newly failing: " + "; ".join(receipt["newly_failing"][:20]))
        for run in receipt["runs"]:
            if run["exit"] not in (0, None):
                lines.append(f"{run['name']} output (tail):\n{run['output'][-1500:]}")
    if receipt["isolation"]:
        lines.append("Couldn't re-point these copied files at the copy: " + ", ".join(receipt["isolation"]))
    return "\n".join(lines)
