"""Interactive terminal: your login shell on a PTY, shown in the browser with xterm.js over a WebSocket.

This is a real shell running as you, so the endpoint is locked down (see server.py):
  - the server only listens on localhost, and the Host header must be localhost
  - the browser's Origin must be this server
  - every connection must present a random token generated at startup and embedded in the page

Protocol: the browser sends JSON text frames {"type": "input", "data": str} and
{"type": "resize", "cols": int, "rows": int}; the server sends terminal output as text frames.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import fcntl
import json
import os
import pty
import signal
import struct
import subprocess
import sys
import termios
from pathlib import Path

from starlette.websockets import WebSocket, WebSocketDisconnect

EOF_MARK = b"\x00EOF"


# Runs in the new child process (no threads), so it can safely make the PTY its controlling terminal before
# becoming the shell. Spawning via subprocess avoids forkpty() inside the multi-threaded server.
_HELPER = (
    "import fcntl, os, sys, termios\n"
    "os.setsid()\n"
    "fcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
    "try:\n    os.chdir(sys.argv[1])\nexcept OSError:\n    pass\n"
    "os.execvp(sys.argv[2], [sys.argv[2], '-l'])\n"
)


class Pty:
    def __init__(self, cwd: Path, shell: str | None = None, cols: int = 100, rows: int = 30):
        self.shell = shell or os.environ.get("SHELL") or "/bin/bash"
        env = dict(os.environ)
        env.pop("VIRTUAL_ENV", None)  # don't hand codepilot's own venv to the user's shell
        env.update({"TERM": "xterm-256color", "COLORTERM": "truecolor", "CODEPILOT_TERMINAL": "1"})
        master, slave = pty.openpty()
        self.proc = subprocess.Popen([sys.executable, "-I", "-c", _HELPER, str(cwd), self.shell],
                                     stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
        os.close(slave)
        self.pid, self.fd = self.proc.pid, master
        self.resize(cols, rows)
        fcntl.fcntl(master, fcntl.F_SETFL, fcntl.fcntl(master, fcntl.F_GETFL) | os.O_NONBLOCK)

    def resize(self, cols: int, rows: int) -> None:
        cols, rows = max(10, min(int(cols), 500)), max(2, min(int(rows), 200))
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def write(self, data: str) -> None:
        payload = data.encode()
        while payload:
            try:
                payload = payload[os.write(self.fd, payload):]
            except BlockingIOError:
                continue

    def read(self) -> bytes:
        try:
            return os.read(self.fd, 65536)
        except BlockingIOError:
            return b""
        except OSError:  # EIO once the shell has exited
            return EOF_MARK

    def close(self) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self.pid, signal.SIGHUP)  # the shell leads its own session, so pgid == pid
        with contextlib.suppress(OSError):
            os.close(self.fd)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.proc.wait(timeout=2)


async def serve(ws: WebSocket, cwd: Path) -> None:
    """Bridge one WebSocket (already authorised and accepted) to a fresh shell."""
    term = Pty(cwd)
    loop = asyncio.get_running_loop()
    out: asyncio.Queue[bytes] = asyncio.Queue()
    loop.add_reader(term.fd, lambda: out.put_nowait(term.read()))
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    async def pump_out() -> None:
        while True:
            chunk = await out.get()
            if chunk == EOF_MARK:
                await ws.send_text("\r\n[shell exited]\r\n")
                await ws.close()
                return
            if chunk:
                await ws.send_text(decoder.decode(chunk))

    async def pump_in() -> None:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "input":
                term.write(str(msg.get("data", "")))
            elif msg.get("type") == "resize":
                term.resize(msg.get("cols", 100), msg.get("rows", 30))

    tasks = [asyncio.create_task(pump_out()), asyncio.create_task(pump_in())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        loop.remove_reader(term.fd)
        term.close()
