"""The /static/ mount: every script and stylesheet is revalidated on each load.

Without a Cache-Control header the browser guesses how long a file stays fresh from its age (heuristic freshness), so
after an upgrade it could run a new app.js with an old cached helper script ("stepWaiting is not defined"). `no-cache`
makes it ask every time; an unchanged file still answers 304 from its ETag, so a load costs one round trip, not bytes.
"""
import os

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

CACHE_CONTROL = "no-cache"


class RevalidatedStaticFiles(StaticFiles):
    def file_response(self, full_path: str | os.PathLike[str], stat_result: os.stat_result, scope: Scope,
                      status_code: int = 200) -> Response:
        # Set on whatever comes back, the file or its 304, so both carry it.
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = CACHE_CONTROL
        return response
