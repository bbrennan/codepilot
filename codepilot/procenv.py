"""How codepilot runs other programs: never interactively.

Nobody can type into a command codepilot runs, so anything that waits for a person (an editor for a commit message,
a credential prompt, a pager, stdin) would just hang until the timeout. The environment turns those off, stdin is
closed, and each command gets its own process group so a timeout stops everything it started, not only the shell.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

NONINTERACTIVE = {
    "GIT_TERMINAL_PROMPT": "0",  # no username/password prompts
    "GIT_EDITOR": ":",  # `git commit` with no -m aborts; `rebase --continue` keeps the message
    "GIT_SEQUENCE_EDITOR": ":",  # `rebase -i` can't be edited here
    "GIT_PAGER": "cat", "PAGER": "cat", "GH_PAGER": "cat",
    "GH_PROMPT_DISABLED": "1",
    "GCM_INTERACTIVE": "never",  # Git Credential Manager
}


def env(base: dict | None = None) -> dict:
    e = dict(os.environ if base is None else base)
    e.pop("VIRTUAL_ENV", None)  # don't leak codepilot's own venv into the workspace's tooling
    e.update(NONINTERACTIVE)
    return e


def run(argv: list[str], cwd: Path | str | None, timeout: float, environ: dict | None = None
        ) -> tuple[int, str, str]:
    """(exit code, stdout, stderr). Raises subprocess.TimeoutExpired after killing the whole process group."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env() if environ is None else environ, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                            start_new_session=True)  # no controlling terminal either: ssh can't prompt on it
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        # Don't wait for EOF: a child that started its own session survives the kill and keeps the pipes open.
        for pipe in (proc.stdout, proc.stderr):
            pipe.close()
        proc.wait()
        raise
    return proc.returncode, out, err
