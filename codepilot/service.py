"""Run codepilot in the background, without keeping a terminal open.

`codepilot start` launches the server as a detached process (log: ~/.codepilot/server.log) and opens it,
in a chromeless app window when Chrome, Edge, Brave or Chromium is installed. `codepilot stop` ends it.
`codepilot app` installs a macOS launcher (~/Applications/Codepilot.app) that stays in the Dock: clicking it
opens the window again, including after it was minimized or left on a display that was unplugged.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import window
from .config import Config

STATIC = Path(__file__).parent / "static"
APP_BROWSERS = ["Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium", "Arc"]


def _url(cfg: Config, port: int | None = None) -> str:
    host = "127.0.0.1" if cfg.host in ("0.0.0.0", "") else cfg.host
    return f"http://{host}:{port or cfg.port}"


def _files(cfg: Config) -> tuple[Path, Path]:
    return cfg.home / "server.pid", cfg.home / "server.log"


def is_up(url: str, timeout: float = 1.5) -> bool:
    """True if a codepilot server answers at url."""
    try:
        with urllib.request.urlopen(url + "/api/config", timeout=timeout) as resp:
            return resp.status == 200 and "provider" in json.loads(resp.read() or b"{}")
    except (OSError, ValueError):
        return False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def running(cfg: Config) -> dict | None:
    """The background server's record, if it is still running."""
    pid_file, _ = _files(cfg)
    try:
        info = json.loads(pid_file.read_text())
    except (OSError, ValueError):
        return None
    if _pid_alive(int(info.get("pid", 0))):
        return info
    pid_file.unlink(missing_ok=True)
    return None


def app_profile(cfg: Config) -> Path | None:
    """The browser profile the app window uses: its own (no extensions in the page, and a window position Chrome
    remembers per display, apart from your everyday windows), unless CODEPILOT_APP_PROFILE=0 keeps your usual one.
    A frame saved on a display that is no longer plugged in is moved back; see window.py."""
    return None if os.environ.get("CODEPILOT_APP_PROFILE", "1").strip() == "0" else cfg.home / "chrome"


def spawn_window(url: str, app_window: bool = True, profile: Path | None = None, extra: list[str] | None = None) -> bool:
    """Open the app window, with `extra` Chrome arguments (a frame on the current display). False if no Chromium
    browser is installed, in which case the caller opens a normal tab."""
    args = [f"--app={url}"]
    if profile is not None:
        args += [f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check"]
    args += list(extra or [])
    if app_window and sys.platform == "darwin":
        for name in ([os.environ["CODEPILOT_APP_BROWSER"]] if os.environ.get("CODEPILOT_APP_BROWSER") else []) \
                + APP_BROWSERS:
            if subprocess.run(["open", "-Ra", name], capture_output=True).returncode == 0:
                subprocess.Popen(["open", "-na", name, "--args", *args],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
    elif app_window:
        for exe in ("google-chrome", "microsoft-edge", "brave-browser", "chromium", "chromium-browser"):
            if shutil.which(exe):
                subprocess.Popen([exe, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return True
    return False


def open_window(url: str, app_window: bool = True, profile: Path | None = None) -> None:
    """Open codepilot in its own chromeless window if a Chromium browser is available, else the default browser.

    On macOS, a window left minimized or on a display that was unplugged is opened on a display that is
    plugged in. The browser for that profile is quit first, because Chrome would otherwise put the window
    back where it saved it."""
    extra: list[str] = []
    if app_window and profile is not None and sys.platform == "darwin":
        extra = window.recover(profile, asked=True) or []
    if spawn_window(url, app_window, profile, extra):
        return
    webbrowser.open(url)


def _present(cfg: Config, env_path: Path | None, url: str, app_window: bool, open_ui: bool) -> None:
    if not open_ui:
        return
    open_window(url, app_window, app_profile(cfg))
    if app_window and sys.platform == "darwin":
        try:
            window.ensure_dock(cfg.home, sys.executable, env_path)
        except (OSError, subprocess.CalledProcessError):
            pass  # the window is already open; a missing Dock icon is the old behaviour


def login_shell() -> str:
    try:
        import pwd

        return os.environ.get("SHELL") or pwd.getpwuid(os.getuid()).pw_shell or "/bin/bash"
    except (ImportError, KeyError):
        return os.environ.get("SHELL") or "/bin/bash"


def shell_environment(timeout: float = 8.0) -> dict[str, str]:
    """The environment your login shell sets up (PATH, AWS_PROFILE, nvm, ...), as VS Code does at launch.

    Apps opened from Finder or the Dock get a bare environment, so tests, gh, git and AWS settings from your
    shell profile would otherwise be missing."""
    mark = "__CODEPILOT_ENV__"
    try:
        out = subprocess.run([login_shell(), "-ilc", f"printf '{mark}'; env -0"], capture_output=True,
                             timeout=timeout, stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    _, _, body = out.decode(errors="replace").partition(mark)
    env = dict(item.split("=", 1) for item in body.split("\0") if "=" in item)
    for noise in ("PWD", "OLDPWD", "SHLVL", "_", "TERM_SESSION_ID"):
        env.pop(noise, None)
    return env


def start(cfg: Config, env_path: Path | None, port: int | None = None, open_ui: bool = True,
          app_window: bool = True, wait: float = 30.0) -> int:
    from .version import fingerprint

    url = _url(cfg, port)
    pid_file, log_file = _files(cfg)
    info = running(cfg)
    if info and info.get("version") != fingerprint():
        # Started before the code changed (e.g. a git pull): reopening the window would keep running the old
        # code, so restart it.
        print("codepilot was updated since the background server started; restarting it…")
        stop(cfg, quiet=True)
        info = None
    if info or is_up(url):
        print(f"codepilot is already running at {info['url'] if info else url}")
        if not info and server_stale(url):
            print("  Note: that server runs older code than this checkout (it wasn't started with `codepilot start`).\n"
                  "  Stop it where it runs (Ctrl+C), then run `codepilot start` again.")
        _present(cfg, env_path, info["url"] if info else url, app_window, open_ui)
        return 0
    cfg.home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if not os.environ.get("TERM"):  # launched from Finder/Dock, not a terminal
        env = {**shell_environment(), **{k: v for k, v in os.environ.items() if k.startswith("CODEPILOT_")}}
    cmd = [sys.executable, "-u", "-m", "codepilot", *(["--env-file", str(env_path)] if env_path else []),
           "serve", "--no-browser", "--host", cfg.host, "--port", str(port or cfg.port)]
    with open(log_file, "ab") as log:
        log.write(f"\n=== codepilot start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        log.flush()
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, cwd=str(Path.home()), env=env or None)
    pid_file.write_text(json.dumps({"pid": proc.pid, "url": url, "env": str(env_path or ""),
                                    "started": time.time(), "version": fingerprint()}))
    deadline = time.time() + wait
    while time.time() < deadline:
        if is_up(url):
            print(f"codepilot is running in the background at {url}")
            print(f"  log: {log_file}   stop: codepilot stop")
            _present(cfg, env_path, url, app_window, open_ui)
            return 0
        if proc.poll() is not None:
            break
        time.sleep(0.3)
    pid_file.unlink(missing_ok=True)
    print(f"codepilot failed to start; see {log_file}:\n", file=sys.stderr)
    print(tail(log_file, 30), file=sys.stderr)
    return 1


def server_stale(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/api/config", timeout=1.5) as resp:
            return bool(json.loads(resp.read() or b"{}").get("stale"))
    except (OSError, ValueError):
        return False


def restart(cfg: Config, env_path: Path | None, port: int | None = None, open_ui: bool = True,
            app_window: bool = True) -> int:
    stop(cfg, quiet=True)
    return start(cfg, env_path, port, open_ui, app_window)


def stop(cfg: Config, quiet: bool = False) -> int:
    info = running(cfg)
    pid_file, _ = _files(cfg)
    if not info and quiet:
        return 0
    if not info:
        print("codepilot isn't running in the background" +
              (f" (something else answers at {_url(cfg)}; stop it where you started it)" if is_up(_url(cfg)) else ""))
        return 0
    pid = int(info["pid"])
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    else:
        os.kill(pid, signal.SIGKILL)
    pid_file.unlink(missing_ok=True)
    print(f"stopped codepilot (pid {pid})")
    return 0


def status(cfg: Config) -> int:
    info = running(cfg)
    _, log_file = _files(cfg)
    if info:
        from .version import fingerprint

        up = is_up(info["url"])
        print(f"running: pid {info['pid']} at {info['url']}{'' if up else ' (not answering yet)'}")
        if info.get("version") != fingerprint():
            print("  out of date: the code changed since it started. Run `codepilot restart` (or `make restart`).")
        print(f"started: {time.strftime('%Y-%m-%d %H:%M', time.localtime(info['started']))}  env: {info['env'] or '-'}")
        print(f"log: {log_file}")
        return 0
    if is_up(_url(cfg)):
        print(f"running in the foreground (e.g. make serve) at {_url(cfg)}")
        return 0
    print("not running. Start it with: codepilot start")
    return 3


def tail(path: Path, lines: int = 60) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log yet)"


def logs(cfg: Config, lines: int = 60, follow: bool = False) -> int:
    _, log_file = _files(cfg)
    print(tail(log_file, lines))
    if follow and log_file.exists():
        with open(log_file, errors="replace") as fh:
            fh.seek(0, os.SEEK_END)
            try:
                while True:
                    line = fh.readline()
                    if line:
                        print(line, end="", flush=True)
                    else:
                        time.sleep(0.5)
            except KeyboardInterrupt:
                pass
    return 0


def install_app(cfg: Config, env_path: Path | None, dest: Path | None = None) -> int:
    """Write ~/Applications/Codepilot.app, a Dock launcher for `codepilot start`.

    It stays running, unlike a shell script that exits: clicking the icon opens the window again after it was
    minimized or left on a display that was unplugged."""
    if sys.platform != "darwin":
        print("`codepilot app` makes a macOS app. Elsewhere, run `codepilot start` (for example from a desktop "
              "shortcut or your login items).")
        return 2
    app = (dest or Path.home() / "Applications") / "Codepilot.app"
    env_args = f'--env-file "{env_path}" ' if env_path else ""
    try:
        window.write_dock_app(app, sys.executable, env_path, cfg.home / "launcher.log", STATIC / "codepilot.icns")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"couldn't install {app}: {exc}", file=sys.stderr)
        return 1
    print(f"Installed {app}")
    print("  Open it from Finder, Spotlight or Launchpad, or drag it to the Dock. It stays there;")
    print("  click it to bring the window back.")
    print(f"  It runs: {sys.executable} -m codepilot {env_args}start")
    print("  Re-run `codepilot app` if you move this checkout or its virtualenv.")
    return 0
