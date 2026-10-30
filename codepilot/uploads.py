"""Saving files the user drops into the explorer.

Same trust rules as the explorer's own file operations: the destination must stay inside the workspace (symlinks
that lead out are refused), nothing is overwritten unless the user confirmed, and `.git` is off limits however it is
reached (a dropped hook would run on the next commit). The write goes to a temporary file first, so a failure never
leaves half a file, and "don't overwrite" is decided by the filesystem (a hard link fails if the name exists), not by
a check that another upload could race past.
"""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
from pathlib import Path, PurePath

from .tools import ToolContext, ToolError

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
NEW_FILE_MODE = 0o644  # mkstemp makes 0600; a dropped file should be as readable as one made any other way


class UploadError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _plain_name(name: str) -> bool:
    """One path component, with no separator or drive of any platform (Path.name drops them on Windows)."""
    return name not in ("", ".", "..") and PurePath(name).name == name and "\\" not in name and ":" not in name


def store_upload(ctx: ToolContext, rel: str, body: bytes, replace: bool = False) -> dict:
    rel = (rel or "").strip()
    parts = rel.split("/")
    if not rel or rel.startswith(("~", "/")) or "\0" in rel or not all(_plain_name(p) for p in parts):
        raise UploadError("Enter a file name inside the workspace.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise UploadError(f"{rel} is larger than {MAX_UPLOAD_BYTES // 1048576} MB.", 413)
    try:
        parent = ctx.resolve("/".join(parts[:-1]) or ".", must_exist=False)
    except ToolError as exc:
        raise UploadError(str(exc)) from None
    target = parent / parts[-1]
    # Checked on the resolved location too, so a link to .git and ".GIT" on a case-insensitive disk are caught.
    if any(p.lower() == ".git" for p in (*parent.relative_to(ctx.root).parts, parts[-1])):
        raise UploadError("Files can't be dropped into .git.")
    if target.is_symlink():
        raise UploadError(f"{rel} is a link; not writing through it.", 409)
    if target.is_dir():
        raise UploadError(f"{rel} is a folder.", 409)
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".upload-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        if replace and target.exists():
            shutil.copymode(target, tmp)  # keep an existing file's permissions, e.g. a script's execute bits
            os.replace(tmp, target)
        else:
            os.chmod(tmp, NEW_FILE_MODE)
            _publish_new(tmp, target, rel)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)
    return {"path": ctx.rel(target), "size": len(body), "mtime": str(target.stat().st_mtime_ns)}


def _publish_new(tmp: str, target: Path, rel: str) -> None:
    """Give `tmp` its final name only if nothing has that name, atomically."""
    try:
        os.link(tmp, target)  # fails if the name exists, even if another upload created it a moment ago
    except FileExistsError:
        raise UploadError(f"{rel} already exists.", 409) from None
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV, errno.EACCES):
            raise
        if target.exists():  # a filesystem without hard links: best effort
            raise UploadError(f"{rel} already exists.", 409) from None
        os.replace(tmp, target)
