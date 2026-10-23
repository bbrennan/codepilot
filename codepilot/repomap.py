"""A compact symbol map of the workspace (Aider-style), so the model starts oriented.

Python files are parsed with `ast`; other languages use light regexes for top-level declarations.
The map lists `path` then `  line: kind name(signature)` rows, source files before tests, shallow
paths first, and stops at a character budget.
"""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path

from .mentions import _all_files

SOURCE_EXTS = {".py", ".js", ".jsx", ".mjs", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb", ".cs", ".swift",
               ".php", ".scala", ".c", ".h", ".cpp", ".hpp"}
DECL = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:public\s+|private\s+|protected\s+|static\s+|abstract\s+|final\s+)*"
    r"(?:async\s+)?(?P<kind>function|class|interface|type|enum|struct|trait|impl|func|fn|def|module|object)\s+"
    r"(?P<name>[A-Za-z_][\w]*)")
ARROW = re.compile(r"^\s*export\s+(?:const|let)\s+(?P<name>[A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(")
MAX_FILE_BYTES = 400_000
_cache: dict[str, tuple[float, str]] = {}


def _py_symbols(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    rows = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rows.append(f"{node.lineno}: def {node.name}({_args(node)})")
        elif isinstance(node, ast.ClassDef):
            rows.append(f"{node.lineno}: class {node.name}")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        not sub.name.startswith("_") or sub.name == "__init__"):
                    rows.append(f"{sub.lineno}:   .{sub.name}({_args(sub)})")
    return rows


def _args(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    names = [a.arg for a in fn.args.args if a.arg not in ("self", "cls")]
    if fn.args.vararg:
        names.append("*" + fn.args.vararg.arg)
    if fn.args.kwarg:
        names.append("**" + fn.args.kwarg.arg)
    out = ", ".join(names)
    return out if len(out) < 60 else out[:57] + "..."


def _generic_symbols(text: str) -> list[str]:
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        if len(line) > 300:
            continue
        m = DECL.match(line) or ARROW.match(line)
        if m:
            kind = m.groupdict().get("kind") or "const"
            indent = "  " if line[:1] in (" ", "\t") else ""
            rows.append(f"{n}: {indent}{kind} {m.group('name')}")
        if len(rows) >= 60:
            break
    return rows


def _rank(path: str) -> tuple:
    p = path.lower()
    is_test = any(t in p for t in ("test", "spec", "fixture", "mock", "example"))
    return (is_test, p.count("/"), p)


def build(root: Path, budget: int = 12_000) -> str:
    """Symbol map for root, cached briefly. Empty string if nothing useful was found."""
    key = f"{root}:{budget}"
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < 30:
        return hit[1]
    files = sorted((f for f in _all_files(root) if Path(f).suffix in SOURCE_EXTS), key=_rank)
    parts, used, skipped = [], 0, 0
    for rel in files:
        path = root / rel
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(errors="replace")
        except OSError:
            continue
        rows = _py_symbols(text) if rel.endswith(".py") else _generic_symbols(text)
        if not rows:
            continue
        block = rel + "\n" + "\n".join("  " + r for r in rows) + "\n"
        if used + len(block) > budget:
            skipped += 1
            continue
        parts.append(block)
        used += len(block)
    out = "".join(parts)
    if skipped:
        out += f"[{skipped} more source files not shown; use list_files / search_code]\n"
    _cache[key] = (time.monotonic(), out)
    return out
