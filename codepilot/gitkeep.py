"""Discard's kept copy (spec git-changes 4.2, 4.3): the one action in the Changes view that destroys work keeps what
it throws away in codepilot's trash, as Delete does, and Undo puts it back unless something newer is there.

The file is moved, never read: a rename where the trash is on the same disk, a streamed copy where it isn't. A symlink
is moved as a link, never followed. `resolve(name)` is the server's own path check (`workspace_path`, as every other file
operation uses), so nothing here can reach outside the session's folders.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from collections.abc import Callable
from pathlib import Path

Resolve = Callable[[str], Path]


class ChangedSince(Exception):
    """Undo would overwrite something newer than the discard: refused, and the kept copy stays in the trash."""


def _there(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def stamp(path: Path) -> str | None:
    """What a file is now, as far as Undo needs to know: None when it's gone. The link itself, never its target."""
    try:
        st = path.lstat()
    except FileNotFoundError:
        return None
    return f"{st.st_mtime_ns}:{st.st_size}"


class Kept:
    """One discard's trash slot: `keep` moves the file out of the way before git puts the last commit's version there,
    `put_back` undoes that when git fails, and `seal` records what the discard left, for Undo to check."""

    def __init__(self, trash: Path, root: Path, resolve: Resolve):
        self.trash, self.root, self.resolve = trash, root, resolve
        self.slot: Path | None = None
        self.name: str | None = None  # the name the kept item had
        self._moved_from: Path | None = None

    def _new_slot(self) -> Path:
        self.slot = self.trash / (time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3))
        self.slot.mkdir(parents=True)
        return self.slot

    def keep(self, name: str) -> None:
        path = self.resolve(name)
        if not _there(path):
            return  # (a deleted file: nothing to keep, git brings the last commit's back)
        if path.is_dir() and not path.is_symlink():
            raise ValueError(f"{name} is a folder (a submodule?): discard its changes in the terminal.")
        shutil.move(str(path), str(self._new_slot() / "item"))
        self.name, self._moved_from = name, path

    def put_back(self) -> None:
        if self.slot is None or self._moved_from is None or _there(self._moved_from):
            return  # (never over something: the kept copy then stays in the trash)
        shutil.move(str(self.slot / "item"), str(self._moved_from))
        shutil.rmtree(self.slot, ignore_errors=True)

    def seal(self, names: list[str], were_absent: list[str], shown: str) -> str:
        """Record the discard: each name's state after it (Undo refuses if one has changed), which names it brought
        back from the last commit (Undo removes them again), and the item's own name. Returns the trash id."""
        slot = self.slot or self._new_slot()
        meta = {"kind": "discard", "root": str(self.root), "path": shown, "deleted": time.time(),
                "item": self.name, "after": {n: stamp(self.resolve(n)) for n in names}, "absent": were_absent}
        (slot / "meta.json").write_text(json.dumps(meta))
        return slot.name


def read(trash: Path, trash_id: str) -> dict | None:
    """A trash slot's record, or None (no such slot, or not a discard's: Delete's slots are the server's)."""
    if not re.fullmatch(r"[\w-]+", trash_id or ""):
        return None
    try:
        meta = json.loads((trash / trash_id / "meta.json").read_text())
    except (OSError, ValueError):
        return None
    return meta if meta.get("kind") == "discard" else None


def undo(trash: Path, trash_id: str, resolve: Resolve) -> dict:
    """Put a discard back: the kept item where it was, and what the discard brought back from the last commit removed
    again. Refused, changing nothing, when any file it touched has changed since (ChangedSince)."""
    meta = read(trash, trash_id)
    if meta is None:
        raise FileNotFoundError("That discard is no longer in the trash.")
    for name, was in meta["after"].items():
        if stamp(resolve(name)) != was:
            raise ChangedSince(f"{name} has changed since it was discarded; not overwriting it.")
    for name in [*meta["absent"], *([meta["item"]] if meta["item"] else [])]:
        path = resolve(name)
        if _there(path):  # (the last commit's version, which the discard wrote: unchanged, as checked above)
            path.unlink()
    if meta["item"]:
        dest = resolve(meta["item"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(trash / trash_id / "item"), str(dest))
    shutil.rmtree(trash / trash_id, ignore_errors=True)
    return {"path": meta["path"]}
