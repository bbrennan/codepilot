"""Which version of codepilot's code is this? A fingerprint of the package's files (Python, page code, skills).

A long-running server compares the fingerprint it started with against the files on disk, so after a
`git pull` it can say it's out of date, and `codepilot start` restarts a background server running old code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PACKAGE = Path(__file__).parent


def fingerprint() -> str:
    h = hashlib.sha1()
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc",):
            st = path.stat()
            h.update(f"{path.relative_to(PACKAGE)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:12]


STARTED = fingerprint()  # the code this process loaded
