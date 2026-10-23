"""Run codepilot in the background, without keeping a terminal open.

`codepilot start` launches the server as a detached process (log: ~/.codepilot/server.log) and opens it,
in a chromeless app window when Chrome, Edge, Brave or Chromium is installed. `codepilot stop` ends it.
`codepilot app` installs a macOS launcher (~/Applications/Codepilot.app) that does the same on double-click,
so codepilot can live in the Dock.
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

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


def open_window(url: str, app_window: bool = True) -> None:
    """Open codepilot in its own chromeless window if a Chromium browser is available, else the default browser."""
    if app_window and sys.platform == "darwin":
        for name in ([os.environ["CODEPILOT_APP_BROWSER"]] if os.environ.get("CODEPILOT_APP_BROWSER") else []) \
                + APP_BROWSERS:
            if subprocess.run(["open", "-Ra", name], capture_output=True).returncode == 0:
                subprocess.Popen(["open", "-na", name, "--args", f"--app={url}"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
    elif app_window:
        for exe in ("google-chrome", "microsoft-edge", "brave-browser", "chromium", "chromium-browser"):
            if shutil.which(exe):
                subprocess.Popen([exe, f"--app={url}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return
    webbrowser.open(url)


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
    url = _url(cfg, port)
    pid_file, log_file = _files(cfg)
    info = running(cfg)
    if info or is_up(url):
        print(f"codepilot is already running at {info['url'] if info else url}")
        if open_ui:
            open_window(info["url"] if info else url, app_window)
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
                                    "started": time.time()}))
    deadline = time.time() + wait
    while time.time() < deadline:
        if is_up(url):
            print(f"codepilot is running in the background at {url}")
            print(f"  log: {log_file}   stop: codepilot stop")
            if open_ui:
                open_window(url, app_window)
            return 0
        if proc.poll() is not None:
            break
        time.sleep(0.3)
    pid_file.unlink(missing_ok=True)
    print(f"codepilot failed to start; see {log_file}:\n", file=sys.stderr)
    print(tail(log_file, 30), file=sys.stderr)
    return 1


def stop(cfg: Config) -> int:
    info = running(cfg)
    pid_file, _ = _files(cfg)
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
        up = is_up(info["url"])
        print(f"running: pid {info['pid']} at {info['url']}{'' if up else ' (not answering yet)'}")
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


LAUNCHER = """#!/bin/bash
# Codepilot launcher, written by `codepilot app`. Starts the server in the background if needed, then opens it.
LOG="$HOME/.codepilot/launcher.log"
mkdir -p "$HOME/.codepilot"
{python} -m codepilot {env_args}start >>"$LOG" 2>&1 ||
  osascript -e 'display alert "Codepilot failed to start" message "See ~/.codepilot/server.log"'
"""


def install_app(cfg: Config, env_path: Path | None, dest: Path | None = None) -> int:
    """Write ~/Applications/Codepilot.app, a double-clickable launcher for `codepilot start`."""
    if sys.platform != "darwin":
        print("`codepilot app` makes a macOS app. Elsewhere, run `codepilot start` (for example from a desktop "
              "shortcut or your login items).")
        return 2
    app = (dest or Path.home() / "Applications") / "Codepilot.app"
    contents = app / "Contents"
    if app.exists():
        shutil.rmtree(app)
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    env_args = f'--env-file "{env_path}" ' if env_path else ""
    script = contents / "MacOS" / "Codepilot"
    script.write_text(LAUNCHER.format(python=f'"{sys.executable}"', env_args=env_args))
    script.chmod(0o755)
    shutil.copy(STATIC / "codepilot.icns", contents / "Resources" / "codepilot.icns")
    with open(contents / "Info.plist", "wb") as fh:
        plistlib.dump({
            "CFBundleName": "Codepilot", "CFBundleDisplayName": "Codepilot", "CFBundleIdentifier": "dev.codepilot.app",
            "CFBundleExecutable": "Codepilot", "CFBundleIconFile": "codepilot", "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "1.0", "LSUIElement": True,  # no lingering Dock icon after launching
        }, fh)
    subprocess.run(["touch", str(app)])  # nudge Finder to pick up the icon
    print(f"Installed {app}")
    print("  Open it from Finder, Spotlight or Launchpad, or drag it to the Dock.")
    print(f"  It runs: {sys.executable} -m codepilot {env_args}start")
    print("  Re-run `codepilot app` if you move this checkout or its virtualenv.")
    return 0
