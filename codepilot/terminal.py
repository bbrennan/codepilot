"""Interactive terminals: your login shell on a PTY, shown in the browser with xterm.js over a WebSocket.

Terminals live on the server, like VS Code's: each keeps running, with its scrollback, while no browser is
attached, so reloading the page or switching panels doesn't lose them. They end when the shell exits, when
the user kills them, or when codepilot stops.

This is a real shell running as you, so the endpoints are locked down (see server.py):
  - the server only listens on localhost, and the Host header must be localhost
  - the browser's Origin must be this server
  - every request must present a random token generated at startup and embedded in the page

WebSocket protocol (/api/terminal?id=...): the browser sends JSON text frames {"type": "input", "data": str}
and {"type": "resize", "cols": int, "rows": int}. The server first replays the terminal's scrollback, then
streams output as text frames. When the shell exits it closes with code 4000 and the exit code as the reason.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from starlette.websockets import WebSocket, WebSocketDisconnect

EXITED = 4000  # WebSocket close code: the shell exited (reason = exit code)
UNKNOWN = 4004  # WebSocket close code: no such terminal
MAX_TERMINALS = 12
SCROLLBACK_CHARS = 256_000


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
        from .service import login_shell

        self.shell = shell or login_shell()
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

    def close(self) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self.pid, signal.SIGHUP)  # the shell leads its own session, so pgid == pid
        with contextlib.suppress(OSError):
            os.close(self.fd)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.proc.wait(timeout=2)


class TerminalLimit(RuntimeError):
    pass


class Terminal:
    """One shell. A reader thread collects its output into a capped scrollback and fans it out to subscribers."""

    def __init__(self, cwd: Path, name: str = "", shell: str | None = None, scrollback: int = SCROLLBACK_CHARS):
        self.id = uuid.uuid4().hex[:12]
        self.cwd = cwd
        self.pty = Pty(cwd, shell)
        self.name = name or Path(self.pty.shell).name
        self.created = time.time()
        self.exit_code: int | None = None
        self.alive = True
        self._scrollback = scrollback
        self._chunks: list[str] = []
        self._size = 0
        self._subs: list[Callable[[str | None], None]] = []
        self._lock = threading.Lock()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._thread = threading.Thread(target=self._pump, name=f"terminal-{self.id}", daemon=True)
        self._thread.start()

    def info(self) -> dict:
        return {"id": self.id, "name": self.name, "cwd": str(self.cwd), "shell": Path(self.pty.shell).name,
                "pid": self.pty.pid, "created": self.created, "alive": self.alive, "exit_code": self.exit_code}

    def _pump(self) -> None:
        while True:
            try:
                ready, _, _ = select.select([self.pty.fd], [], [], 0.5)
                if not ready:
                    continue
                data = os.read(self.pty.fd, 65536)
            except BlockingIOError:
                continue
            except (OSError, ValueError):  # EIO once the shell has exited, EBADF once killed
                break
            if not data:
                break
            self._emit(self._decoder.decode(data))
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.pty.proc.wait(timeout=2)
        self.exit_code = self.pty.proc.returncode
        self.alive = False
        self._emit(None)

    def _emit(self, chunk: str | None) -> None:
        with self._lock:  # fan out under the lock so a new subscriber never misses or repeats a chunk
            if chunk:
                self._chunks.append(chunk)
                self._size += len(chunk)
                if self._size > self._scrollback:
                    text = "".join(self._chunks)[-self._scrollback:]
                    cut = text.find("\n")  # restart on a line boundary, not inside an escape sequence
                    text = text[cut + 1:] if 0 <= cut < 4096 else text
                    self._chunks, self._size = [text], len(text)
            for fn in list(self._subs):
                with contextlib.suppress(Exception):  # a subscriber whose event loop is gone
                    fn(chunk)

    def scrollback(self) -> str:
        with self._lock:
            return "".join(self._chunks)

    def subscribe(self, fn: Callable[[str | None], None]) -> str:
        """Register for output (None means the shell exited) and return the scrollback so far."""
        with self._lock:
            self._subs.append(fn)
            return "".join(self._chunks)

    def unsubscribe(self, fn: Callable[[str | None], None]) -> None:
        with self._lock, contextlib.suppress(ValueError):
            self._subs.remove(fn)

    def write(self, data: str) -> None:
        if self.alive:
            with contextlib.suppress(OSError):
                self.pty.write(data)

    def resize(self, cols: int, rows: int) -> None:
        if self.alive:
            with contextlib.suppress(OSError, ValueError):
                self.pty.resize(cols, rows)

    def kill(self) -> None:
        self.pty.close()
        self._thread.join(timeout=3)


class TerminalManager:
    def __init__(self, max_terminals: int = MAX_TERMINALS, scrollback: int = SCROLLBACK_CHARS,
                 shell: str | None = None):
        self.max_terminals = max_terminals
        self.scrollback = scrollback
        self.shell = shell
        self._terms: dict[str, Terminal] = {}
        self._lock = threading.Lock()

    def create(self, cwd: Path, name: str = "") -> Terminal:
        with self._lock:
            if sum(t.alive for t in self._terms.values()) >= self.max_terminals:
                raise TerminalLimit(f"At most {self.max_terminals} terminals can run at once; close one first.")
            term = Terminal(cwd, name, self.shell, self.scrollback)
            self._terms[term.id] = term
            return term

    def get(self, tid: str) -> Terminal | None:
        return self._terms.get(tid)

    def list(self) -> list[Terminal]:
        return sorted(self._terms.values(), key=lambda t: t.created)

    def kill(self, tid: str) -> bool:
        with self._lock:
            term = self._terms.pop(tid, None)
        if term:
            term.kill()
        return term is not None

    def close_all(self) -> None:
        for tid in list(self._terms):
            self.kill(tid)


async def attach(ws: WebSocket, term: Terminal) -> None:
    """Bridge one WebSocket (already authorised and accepted) to a terminal until either side ends."""
    loop = asyncio.get_running_loop()
    out: asyncio.Queue[str | None] = asyncio.Queue()

    def on_output(chunk: str | None) -> None:
        loop.call_soon_threadsafe(out.put_nowait, chunk)

    history = term.subscribe(on_output)

    async def pump_out() -> None:
        if history:
            await ws.send_text(history)
        if not term.alive:
            await out.put(None)
        while True:
            chunk = await out.get()
            if chunk is None:
                await ws.send_text(f"\r\n[process exited with code {term.exit_code}]\r\n")
                await ws.close(code=EXITED, reason=str(term.exit_code))
                return
            await ws.send_text(chunk)

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
        term.unsubscribe(on_output)
