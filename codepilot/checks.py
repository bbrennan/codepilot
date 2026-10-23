"""Deterministic analysers: linters, type checkers and security scanners the workspace already uses.

Ground truth beats model judgement, so codepilot runs whichever of these are installed (in the workspace's
.venv or node_modules first, then PATH) and hands the model their output. Nothing here is required; missing
tools are simply skipped.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

PER_TOOL_CHARS = 6000


@dataclass
class Check:
    name: str
    kind: str  # lint | types | security
    argv: list[str]
    note: str = ""


def find_bin(root: Path, name: str) -> str | None:
    for cand in (root / ".venv" / "bin" / name, root / "node_modules" / ".bin" / name):
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return shutil.which(name)


def _pyproject(root: Path) -> dict:
    try:
        return tomllib.loads((root / "pyproject.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def detect(root: Path, paths: list[str] | None = None) -> list[Check]:
    targets = paths or ["."]
    checks: list[Check] = []
    py = (root / "pyproject.toml").exists() or (root / "setup.py").exists() or any(root.glob("*.py"))
    tool_cfg = _pyproject(root).get("tool", {})
    if py:
        if b := find_bin(root, "ruff"):
            checks.append(Check("ruff", "lint", [b, "check", "--output-format", "concise", *targets]))
        if (b := find_bin(root, "mypy")) and ("mypy" in tool_cfg or (root / "mypy.ini").exists()):
            uses_config_files = not paths and "files" in tool_cfg.get("mypy", {})
            checks.append(Check("mypy", "types", [b, *([] if uses_config_files else targets)]))
        if (b := find_bin(root, "pyright")) and ("pyright" in tool_cfg or (root / "pyrightconfig.json").exists()):
            checks.append(Check("pyright", "types", [b, *(paths or [])]))
        if b := find_bin(root, "bandit"):
            checks.append(Check("bandit", "security", [b, "-q", "-r", *targets, "-x", "./.venv,./tests"]))
    if (root / "package.json").exists():
        if b := find_bin(root, "eslint"):
            checks.append(Check("eslint", "lint", [b, "-f", "unix", *targets]))
        if (b := find_bin(root, "tsc")) and (root / "tsconfig.json").exists():
            checks.append(Check("tsc", "types", [b, "--noEmit", "--pretty", "false"]))
    if (root / "go.mod").exists():
        if b := find_bin(root, "golangci-lint"):
            checks.append(Check("golangci-lint", "lint", [b, "run"]))
        elif b := shutil.which("go"):
            checks.append(Check("go vet", "lint", [b, "vet", "./..."]))
    if (root / "Cargo.toml").exists() and (b := shutil.which("cargo")):
        checks.append(Check("clippy", "lint", [b, "clippy", "--quiet", "--message-format=short"]))
    if b := find_bin(root, "gitleaks"):
        checks.append(Check("gitleaks", "security",
                            [b, "detect", "--no-git", "--source", ".", "--redact", "--no-banner"]))
    if b := find_bin(root, "semgrep"):
        local = next((c for c in (".semgrep.yml", ".semgrep.yaml", "semgrep.yml") if (root / c).exists()), None)
        checks.append(Check("semgrep", "security", [b, "scan", "--quiet", "--metrics=off", "--error",
                                                    "--config", local or "p/default", *targets],
                            note="" if local else "uses the semgrep registry (needs network)"))
    return checks


def run_all(root: Path, kind: str = "all", paths: list[str] | None = None, timeout: int = 300) -> str:
    checks = [c for c in detect(root, paths) if kind in ("all", c.kind)]
    if not checks:
        return ("No analysers found for this workspace. Useful ones: ruff, mypy or pyright (Python), eslint and "
                "tsc (JS/TS), golangci-lint (Go), cargo clippy (Rust), gitleaks and semgrep (security).")
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    parts = []
    for c in checks:
        try:
            proc = subprocess.run(c.argv, cwd=root, capture_output=True, text=True, timeout=timeout, env=env,
                                  errors="replace", check=False)
            out = (proc.stdout + ("\n" + proc.stderr if proc.stderr.strip() else "")).strip()
            code = proc.returncode
        except subprocess.TimeoutExpired:
            out, code = f"timed out after {timeout}s", -1
        except OSError as exc:
            out, code = str(exc), -1
        if len(out) > PER_TOOL_CHARS:
            out = out[:PER_TOOL_CHARS] + f"\n[... {len(out) - PER_TOOL_CHARS} more characters ...]"
        verdict = "clean" if code == 0 else f"exit {code}"
        parts.append(f"== {c.name} ({c.kind}) {verdict}{' - ' + c.note if c.note else ''} ==\n{out or '(no output)'}")
    return "\n\n".join(parts)


def summary(root: Path) -> list[dict]:
    return [{"name": c.name, "kind": c.kind} for c in detect(root)]


def quick_check(root: Path, rel: str) -> str:
    """Fast, side-effect-free check of one file right after an edit is applied. '' means clean.

    Syntax is checked by compiling/parsing only; no workspace code is executed.
    """
    path = root / rel
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    problems = []
    suffix = path.suffix.lower()
    try:
        if suffix == ".py":
            compile(text, rel, "exec", dont_inherit=True)
        elif suffix == ".json":
            json.loads(text)
        elif suffix == ".toml":
            tomllib.loads(text)
    except SyntaxError as exc:
        problems.append(f"{rel}:{exc.lineno}:{exc.offset or 0}: syntax error: {exc.msg}")
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, ValueError) as exc:
        problems.append(f"{rel}: invalid {suffix[1:]}: {exc}")
    if suffix == ".py" and not problems and (ruff := find_bin(root, "ruff")):
        try:
            proc = subprocess.run([ruff, "check", "--output-format", "concise", rel], cwd=root, capture_output=True,
                                  text=True, timeout=60, check=False)
            if proc.returncode not in (0,) and proc.stdout.strip():
                problems.append("ruff:\n" + "\n".join(proc.stdout.strip().splitlines()[:30]))
        except (OSError, subprocess.SubprocessError):
            pass
    return "\n".join(problems)
