"""@-references in chat ("look at @src/app.py:40-80") and fuzzy file search for the composer.

A reference to a file inside the workspace is attached to the user's message, so the model sees the
content without spending a tool call. Directories attach a file listing. Paths outside the workspace
are left alone (the model can still be asked to open them).
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

MENTION = re.compile(r"(?<![\w@`])@([\w.\-/~]+)(?::(\d+)(?:-(\d+))?)?")
PER_FILE_CHARS = 40_000
TOTAL_CHARS = 120_000
ATTACH_OPEN = "<attached_files>"


def _resolve(root: Path, rel: str) -> Path | None:
    p = Path(rel).expanduser()
    p = (p if p.is_absolute() else root / p).resolve()
    if p != root and root not in p.parents:
        return None
    return p if p.exists() else None


def find_mentions(root: Path | None, text: str) -> list[dict]:
    """Workspace files/dirs referenced with @path or @path:start-end, in order, without duplicates."""
    if root is None:
        return []
    found, seen = [], set()
    for m in MENTION.finditer(text):
        rel, start, end = m.group(1), m.group(2), m.group(3)
        if not start:
            rel = rel.rstrip(".,;:")
        path = _resolve(root, rel)
        if path is None:
            continue
        key = (str(path), start, end)
        if key in seen:
            continue
        seen.add(key)
        first = int(start) if start else None
        found.append({"path": path, "rel": str(path.relative_to(root)) if path != root else ".",
                      "start": first, "end": int(end) if end else first})
    return found


def attachment_block(root: Path | None, text: str) -> tuple[str, list[str]]:
    """Build the <attached_files> block for a message; returns (block, labels)."""
    mentions = find_mentions(root, text)
    if not mentions:
        return "", []
    parts, labels, total = [ATTACH_OPEN], [], 0
    for m in mentions:
        path, rel = m["path"], m["rel"]
        label = rel + (f":{m['start']}-{m['end']}" if m["start"] else "")
        if path.is_dir():
            entries = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir() if not p.name.startswith("."))
            body = "\n".join(entries[:300])
            parts.append(f'<directory path="{rel}">\n{body}\n</directory>')
        else:
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\0" in raw[:4096]:
                parts.append(f'<file path="{rel}">(binary file not attached)</file>')
                labels.append(label)
                continue
            lines = raw.decode(errors="replace").splitlines()
            start = max(1, m["start"] or 1)
            end = min(len(lines), m["end"] or len(lines))
            body = "\n".join(f"{n:>5}  {lines[n - 1]}" for n in range(start, end + 1))
            if len(body) > PER_FILE_CHARS:
                body = body[:PER_FILE_CHARS] + "\n[... truncated; use read_file for the rest ...]"
            if total + len(body) > TOTAL_CHARS:
                parts.append(f'<file path="{rel}">(not attached: attachment budget used up; use read_file)</file>')
                labels.append(label + " (skipped)")
                continue
            total += len(body)
            attrs = f' lines="{start}-{end}"' if m["start"] else ""
            parts.append(f'<file path="{rel}"{attrs}>\n{body}\n</file>')
        labels.append(label)
    parts.append("</attached_files>")
    return "\n".join(parts), labels


def attached_labels(block: str) -> list[str]:
    """Recover display labels from a stored attachment block."""
    out = []
    for m in re.finditer(r'<(?:file|directory) path="([^"]+)"(?: lines="([^"]+)")?', block):
        out.append(m.group(1) + (f":{m.group(2)}" if m.group(2) else ""))
    return out


# -- fuzzy file search ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, list[str]]] = {}


def _all_files(root: Path) -> list[str]:
    hit = _cache.get(str(root))
    if hit and time.monotonic() - hit[0] < 15:
        return hit[1]
    files: list[str] = []
    if (root / ".git").exists():
        proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                              capture_output=True, timeout=30, check=False)
        if proc.returncode == 0:
            files = [p for p in proc.stdout.decode(errors="replace").split("\0") if p]
    if not files:
        from .tools import SKIP_DIRS

        for p in root.rglob("*"):
            if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
                continue
            if p.is_file():
                files.append(str(p.relative_to(root)))
            if len(files) > 50_000:
                break
    files.sort()
    _cache[str(root)] = (time.monotonic(), files)
    return files


def _score(path: str, query: str) -> float | None:
    """Subsequence match; higher is better. Rewards basename hits and contiguous runs."""
    p, q = path.lower(), query.lower()
    base = p.rsplit("/", 1)[-1]
    if q in base:
        return 1000 - len(p) + (500 if base.startswith(q) else 0)
    if q in p:
        return 600 - len(p)
    i, score, run = 0, 0.0, 0
    for ch in p:
        if i < len(q) and ch == q[i]:
            i += 1
            run += 1
            score += run
        else:
            run = 0
    return score - len(p) * 0.1 if i == len(q) else None


def find_files(root: Path, query: str, limit: int = 30) -> list[str]:
    files = _all_files(root)
    if not query:
        return files[:limit]
    scored = [(s, f) for f in files if (s := _score(f, query)) is not None]
    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored[:limit]]
