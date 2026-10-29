"""Saving files the user drops into the explorer.

Same trust rules as the explorer's own file operations: the destination must stay inside the workspace (symlinks
that lead out are refused), nothing is overwritten unless the user confirmed, and `.git` is off limits (a dropped
hook would run on the next commit). The write goes to a temporary file first, so a failure never leaves half a file.
"""

from __future__ import annotations

import os
import tempfile

from .tools import ToolContext, ToolError

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


class UploadError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def store_upload(ctx: ToolContext, rel: str, body: bytes, replace: bool = False) -> dict:
    rel = (rel or "").strip()
    parts = rel.split("/")
    if not rel or rel.startswith(("~", "/")) or "\0" in rel or any(p in ("", ".", "..") for p in parts):
        raise UploadError("Enter a file name inside the workspace.")
    if ".git" in parts:
        raise UploadError("Files can't be dropped into .git.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise UploadError(f"{rel} is larger than {MAX_UPLOAD_BYTES // 1048576} MB.", 413)
    try:
        parent = ctx.resolve("/".join(parts[:-1]) or ".", must_exist=False)
    except ToolError as exc:
        raise UploadError(str(exc)) from None
    target = parent / parts[-1]
    if target.is_symlink():
        raise UploadError(f"{rel} is a link; not writing through it.", 409)
    if target.is_dir():
        raise UploadError(f"{rel} is a folder.", 409)
    if target.exists() and not replace:
        raise UploadError(f"{rel} already exists.", 409)
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".upload-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return {"path": ctx.rel(target), "size": len(body), "mtime": str(target.stat().st_mtime_ns)}
