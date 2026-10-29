"""Turning hostile or malformed request input into a clean 4xx instead of a 500.

`json_body` is the one way routes read a JSON body: it must be an object. `HANDLERS` answers the rest centrally:
a path with a NUL byte or a name the filesystem rejects (too long, not a directory) is the caller's mistake, not
a server failure.
"""

from __future__ import annotations

import errno
import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("codepilot.server")


class BadInput(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


async def json_body(request: Request, optional: bool = False) -> dict:
    """The request's JSON object. With `optional`, an empty body is {}."""
    raw = await request.body()
    if optional and not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise BadInput("The request body isn't valid JSON.") from None
    if not isinstance(data, dict):
        raise BadInput("The request body must be a JSON object.")
    return data


def _json(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _bad_input(request: Request, exc: BadInput) -> JSONResponse:
    return _json(str(exc), exc.status)


async def _os_error(request: Request, exc: OSError) -> JSONResponse:
    if exc.errno in (errno.ENAMETOOLONG, errno.ENOTDIR, errno.EISDIR, errno.ENOENT, errno.EINVAL, errno.ELOOP):
        return _json(f"{exc.strerror or type(exc).__name__}", 400 if exc.errno != errno.ENOENT else 404)
    log.exception("unhandled OSError on %s", request.url.path)
    return _json(f"{type(exc).__name__}: {exc.strerror or exc}", 500)


async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
    if "null byte" in str(exc) or "embedded null" in str(exc):
        return _json("That path contains a NUL character.", 400)
    log.exception("unhandled ValueError on %s", request.url.path)
    return _json(f"{type(exc).__name__}: {exc}", 500)


HANDLERS = {BadInput: _bad_input, OSError: _os_error, ValueError: _value_error}
