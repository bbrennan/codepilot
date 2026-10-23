"""Local persistence: chat sessions and messages (short-term memory), proposals, and per-repo notes."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    tier TEXT NOT NULL,
    auto_approve INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    pending TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    old_text TEXT NOT NULL,
    new_text TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    reported INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL
);
"""


@dataclass
class Session:
    id: str
    repo: str
    title: str
    tier: str
    auto_approve: bool
    summary: str
    pending: dict | None
    created: float
    updated: float
    mode: str = "act"
    context_state: dict | None = None
    model: str = ""  # explicit model chosen in the UI; empty = use the tier's model

    def public(self) -> dict:
        return {
            "id": self.id, "repo": self.repo, "title": self.title, "tier": self.tier,
            "auto_approve": self.auto_approve, "has_summary": bool(self.summary),
            "mode": {"act": "build"}.get(self.mode, self.mode), "model": self.model,
            "pending": self.pending is not None, "created": self.created, "updated": self.updated,
        }


@dataclass
class Proposal:
    id: int
    session_id: str
    path: str
    old_text: str
    new_text: str
    reason: str
    status: str
    before_text: str | None = None
    after_text: str | None = None
    check_text: str | None = None


def _encode(obj: Any) -> Any:
    if isinstance(obj, bytes):
        return {"__b64__": base64.b64encode(obj).decode()}
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_encode(v) for v in obj]
    return obj


def _history_chunks(content: list[dict], size: int = 1200) -> list[str]:
    """Searchable text of one message (text, tool calls, tool results), in pieces small enough to quote."""
    parts: list[str] = []
    for b in content:
        if "text" in b:
            parts.append(b["text"])
        elif "toolUse" in b:
            parts.append(f"[tool {b['toolUse'].get('name')}] {json.dumps(b['toolUse'].get('input') or {})}")
        elif "toolResult" in b:
            parts += [c["text"] for c in b["toolResult"].get("content", []) if c.get("text")]
    text = "\n".join(p for p in parts if p).strip()
    return [text[i:i + size] for i in range(0, len(text), size)] if text else []


def _decode(obj: Any) -> Any:
    if isinstance(obj, dict):
        if set(obj) == {"__b64__"}:
            return base64.b64decode(obj["__b64__"])
        return {k: _decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode(v) for v in obj]
    return obj


class Store:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "notes").mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.home / "codepilot.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Add columns introduced after a database was created."""
        wanted = {"sessions": [("mode", "TEXT NOT NULL DEFAULT 'act'"), ("context_state", "TEXT"),
                               ("model", "TEXT NOT NULL DEFAULT ''")],
                  "proposals": [("before_text", "TEXT"), ("after_text", "TEXT"), ("check_text", "TEXT")]}
        with self._lock, self._db:
            for table, cols in wanted.items():
                have = {r["name"] for r in self._db.execute(f"PRAGMA table_info({table})")}
                for name, decl in cols:
                    if name not in have:
                        self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    # -- sessions -------------------------------------------------------------------------------

    def create_session(self, repo: str, tier: str, auto_approve: bool = False) -> Session:
        now = time.time()
        sid = uuid.uuid4().hex[:12]
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions (id, repo, tier, auto_approve, created, updated, mode)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid, repo, tier, int(auto_approve), now, now, "build"),
            )
        return self.get_session(sid)

    def get_session(self, sid: str) -> Session:
        with self._lock:
            row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
        if row is None:
            raise KeyError(f"no session {sid}")
        return self._session(row)

    def list_sessions(self, limit: int = 50) -> list[Session]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM sessions ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        return [self._session(r) for r in rows]

    def update_session(self, sid: str, **fields: Any) -> None:
        allowed = {"title", "tier", "auto_approve", "summary", "pending", "repo", "mode", "context_state", "model"}
        if not fields or not set(fields) <= allowed:
            raise ValueError(f"bad session fields: {set(fields) - allowed}")
        if "pending" in fields:
            fields["pending"] = None if fields["pending"] is None else json.dumps(_encode(fields["pending"]))
        if "context_state" in fields:
            fields["context_state"] = None if fields["context_state"] is None else json.dumps(fields["context_state"])
        if "auto_approve" in fields:
            fields["auto_approve"] = int(bool(fields["auto_approve"]))
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._lock, self._db:
            self._db.execute(f"UPDATE sessions SET {cols}, updated = ? WHERE id = ?",
                             (*fields.values(), time.time(), sid))

    def delete_session(self, sid: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM sessions WHERE id = ?", (sid,))

    @staticmethod
    def _session(row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"], repo=row["repo"], title=row["title"], tier=row["tier"],
            auto_approve=bool(row["auto_approve"]), summary=row["summary"],
            pending=_decode(json.loads(row["pending"])) if row["pending"] else None,
            created=row["created"], updated=row["updated"], mode=row["mode"] or "act",
            context_state=json.loads(row["context_state"]) if row["context_state"] else None,
            model=row["model"] or "",
        )

    # -- messages -------------------------------------------------------------------------------

    def add_message(self, sid: str, role: str, content: list[dict]) -> int:
        now = time.time()
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO messages (session_id, role, content, created) VALUES (?, ?, ?, ?)",
                (sid, role, json.dumps(_encode(content)), now),
            )
            self._db.execute("UPDATE sessions SET updated = ? WHERE id = ?", (now, sid))
            return cur.lastrowid

    def messages(self, sid: str, include_archived: bool = False) -> list[tuple[int, dict]]:
        sql = "SELECT id, role, content FROM messages WHERE session_id = ?"
        if not include_archived:
            sql += " AND archived = 0"
        with self._lock:
            rows = self._db.execute(sql + " ORDER BY id", (sid,)).fetchall()
        return [(r["id"], {"role": r["role"], "content": _decode(json.loads(r["content"]))}) for r in rows]

    def live_messages(self, sid: str) -> list[dict]:
        return [m for _, m in self.messages(sid)]

    def last_message(self, sid: str) -> tuple[int, dict] | None:
        rows = self.messages(sid)
        return rows[-1] if rows else None

    def replace_content(self, mid: int, content: list[dict]) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE messages SET content = ? WHERE id = ?", (json.dumps(_encode(content)), mid))

    def is_archived(self, mid: int) -> bool:
        with self._lock:
            row = self._db.execute("SELECT archived FROM messages WHERE id = ?", (mid,)).fetchone()
        return bool(row and row["archived"])

    def delete_messages_from(self, sid: str, mid: int) -> int:
        """Delete a message and everything after it in the session (rewinding the conversation)."""
        with self._lock, self._db:
            return self._db.execute("DELETE FROM messages WHERE session_id = ? AND id >= ?", (sid, mid)).rowcount

    def archive_messages(self, sid: str, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock, self._db:
            self._db.executemany("UPDATE messages SET archived = 1 WHERE session_id = ? AND id = ?",
                                 [(sid, i) for i in ids])

    def search_history(self, sid: str, query: str, scope: str = "session", limit: int = 8) -> list[dict]:
        """BM25 keyword search over conversation history that is no longer in the model's context.

        scope "session": this session's archived (compacted) messages. scope "workspace": also every
        message of earlier sessions on the same folder. Built in memory per query; histories are small.
        """
        terms = re.findall(r"\w{2,}", query)
        if not terms:
            return []
        sql = "SELECT m.id, m.session_id, m.role, m.content, m.created, s.title FROM messages m " \
              "JOIN sessions s ON s.id = m.session_id WHERE (m.session_id = ? AND m.archived = 1)"
        args: list[Any] = [sid]
        if scope == "workspace":
            sql += " OR (m.session_id != ? AND s.repo = (SELECT repo FROM sessions WHERE id = ?) AND s.repo != '')"
            args += [sid, sid]
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        fts = sqlite3.connect(":memory:")
        fts.execute("CREATE VIRTUAL TABLE h USING fts5(body, mid UNINDEXED, sid UNINDEXED, role UNINDEXED, "
                    "created UNINDEXED, title UNINDEXED)")
        for r in rows:
            for chunk in _history_chunks(_decode(json.loads(r["content"]))):
                fts.execute("INSERT INTO h VALUES (?, ?, ?, ?, ?, ?)",
                            (chunk, r["id"], r["session_id"], r["role"], r["created"], r["title"]))
        match = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
        hits = fts.execute("SELECT body, mid, sid, role, created, title FROM h WHERE h MATCH ? "
                           "ORDER BY bm25(h) LIMIT ?", (match, limit)).fetchall()
        fts.close()
        return [{"text": b, "message_id": m, "session_id": s, "role": ro, "created": c, "session_title": t}
                for b, m, s, ro, c, t in hits]

    # -- proposals ------------------------------------------------------------------------------

    def add_proposal(self, sid: str, path: str, old_text: str, new_text: str, reason: str,
                     pid: int | None = None) -> Proposal:
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO proposals (id, session_id, path, old_text, new_text, reason, created)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, sid, path, old_text, new_text, reason, time.time()),
            )
        return self.get_proposal(cur.lastrowid)

    def get_proposal(self, pid: int) -> Proposal:
        with self._lock:
            row = self._db.execute("SELECT * FROM proposals WHERE id = ?", (pid,)).fetchone()
        if row is None:
            raise KeyError(f"no proposal {pid}")
        return Proposal(row["id"], row["session_id"], row["path"], row["old_text"], row["new_text"],
                        row["reason"], row["status"], row["before_text"], row["after_text"], row["check_text"])

    def list_proposals(self, sid: str) -> list[Proposal]:
        with self._lock:
            rows = self._db.execute("SELECT id FROM proposals WHERE session_id = ? ORDER BY id", (sid,)).fetchall()
        return [self.get_proposal(r["id"]) for r in rows]

    def set_proposal_status(self, pid: int, status: str) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE proposals SET status = ?, reported = 0 WHERE id = ?", (status, pid))

    def record_applied(self, pid: int, before: str | None, after: str, check: str = "") -> None:
        """Mark applied, keep before/after text for undo, and any post-apply check findings."""
        with self._lock, self._db:
            self._db.execute("UPDATE proposals SET status = 'applied', reported = 0, before_text = ?, after_text = ?, "
                             "check_text = ? WHERE id = ?", (before, after, check or None, pid))

    def take_unreported_outcomes(self, sid: str) -> list[Proposal]:
        """Proposals the user has acted on since the model last heard about them."""
        with self._lock, self._db:
            rows = self._db.execute(
                "SELECT id FROM proposals WHERE session_id = ? AND status != 'pending' AND reported = 0 ORDER BY id",
                (sid,)).fetchall()
            self._db.executemany("UPDATE proposals SET reported = 1 WHERE id = ?", [(r["id"],) for r in rows])
        return [self.get_proposal(r["id"]) for r in rows]

    # -- token usage ----------------------------------------------------------------------------

    def add_usage(self, sid: str, model: str, usage: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO usage (session_id, model, input_tokens, output_tokens, cache_read, cache_write,"
                " created) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid, model, usage.get("inputTokens", 0), usage.get("outputTokens", 0),
                 usage.get("cacheReadInputTokens", 0), usage.get("cacheWriteInputTokens", 0), time.time()),
            )

    def usage(self, sid: str) -> dict:
        with self._lock:
            rows = self._db.execute(
                "SELECT model, COUNT(*) AS calls, SUM(input_tokens) AS input, SUM(output_tokens) AS output, "
                "SUM(cache_read) AS cache_read, SUM(cache_write) AS cache_write FROM usage WHERE session_id = ? "
                "GROUP BY model", (sid,)).fetchall()
        return {"by_model": [dict(r) for r in rows]}

    # -- per-repo notes (memory that outlives a session) ---------------------------------------

    def notes_path(self, repo: str) -> Path:
        resolved = str(Path(repo).expanduser().resolve())
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(resolved).name)[:40]
        digest = hashlib.sha1(resolved.encode()).hexdigest()[:8]
        return self.home / "notes" / f"{slug}-{digest}.md"

    def read_notes(self, repo: str) -> str:
        path = self.notes_path(repo)
        return path.read_text() if path.exists() else ""

    def add_note(self, repo: str, note: str) -> None:
        path = self.notes_path(repo)
        with self._lock, path.open("a") as fh:
            fh.write(f"- {note.strip()}\n")
