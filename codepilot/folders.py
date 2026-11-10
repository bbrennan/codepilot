"""A session's folders: its main folder (`Session.repo`, where relative paths point, tests run and specs live) plus the
folders the user adds (`Session.folders`), such as another repo. Files in an added folder are named by their full path:
two `src/` folders, or a folder named like a subdirectory, can't be confused."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def added(sess) -> list[Path]:
    """A session's added folders, resolved."""
    return [Path(p).expanduser().resolve() for p in getattr(sess, "folders", None) or []]


def inside(path: Path, roots: Sequence[Path]) -> bool:
    """Is this (resolved) path one of these folders or in one?"""
    return any(path == r or r in path.parents for r in roots)


def check(raw: str, main: Path | None, added: Sequence[Path]) -> Path:
    """A folder to add, resolved; ValueError says why it can't be. It must be a directory that isn't one of the
    session's folders, inside one (its files would have two names), or around one."""
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"{path} doesn't exist")
    if not path.is_dir():
        raise ValueError(f"{path} isn't a folder")
    for have in [Path(p).expanduser().resolve() for p in [*([main] if main else []), *added]]:
        if path == have:
            raise ValueError(f"{path} is already in this session")
        if have in path.parents:
            raise ValueError(f"{path} is inside {have}, which is already in this session")
        if path in have.parents:
            raise ValueError(f"{path} contains {have}, which is already in this session: remove that first")
    return path


def make_main(main: str, added: Sequence[str], new_main: str) -> tuple[str, list[str]]:
    """The session's folders with `new_main` as the main one, the old main folder added in its place."""
    want = Path(new_main).expanduser().resolve()
    rest = [Path(p).expanduser().resolve() for p in added]
    if want not in rest:
        raise ValueError(f"{want} isn't one of this session's folders")
    return str(want), [str(Path(main).expanduser().resolve()) if p == want else str(p) for p in rest]


def prompt_line(added: Sequence[Path]) -> str:
    """What codepilot is told about the added folders ("" without any)."""
    if not added:
        return ""
    return ("Added folders (also yours to read, search and change; name their files by full path, e.g. "
            f"{Path(added[0]) / 'README.md'}): " + ", ".join(str(p) for p in added)
            + ". Relative paths are in the workspace above.")


def patch(main: str, have: Sequence[str], data: dict) -> dict:
    """The session fields a PATCH asks for: `folders` (the whole list of added folders, so removing one is sending the
    rest), `make_main` (an added folder), or a new main folder `repo` (added folders it overlaps are dropped)."""
    if data.get("make_main"):
        repo, rest = make_main(main, have, str(data["make_main"]))
        return {"repo": repo, "folders": rest}
    if "folders" in data:
        raw = data["folders"]
        if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
            raise ValueError("folders must be a list of paths")
        kept = [Path(p).expanduser().resolve() for p in have]
        root = Path(main).expanduser().resolve() if main else None
        out: list[Path] = []
        for p in raw:
            path = Path(p).expanduser().resolve()
            if path in kept and path not in out:  # already in the session: kept even if it's gone missing
                out.append(path)
            else:
                out.append(check(p, root, out))
        return {"folders": [str(p) for p in out]}
    if data.get("repo"):
        new = Path(str(data["repo"])).expanduser().resolve()
        rest = [p for p in have if not inside(Path(p).resolve(), [new]) and not inside(new, [Path(p).resolve()])]
        return {"folders": rest} if len(rest) != len(have) else {}
    return {}


def missing(sess) -> list[str]:
    """The session's added folders that aren't there any more (moved, deleted, an unmounted drive)."""
    return [p for p in getattr(sess, "folders", None) or [] if not Path(p).expanduser().is_dir()]


def rebased(path: str, old_main: Path, new_main: Path) -> str:
    """A change's path once `new_main` is the main folder: a file in the old main folder gets its full path (it would
    otherwise point at the new main folder's file of the same name), and one in the new main folder a relative one."""
    full = Path(path) if Path(path).is_absolute() else old_main / path
    return str(full.relative_to(new_main)) if inside(full, [new_main]) and full != new_main else str(full)
