"""Keep the macOS app window on a display that is plugged in.

`open -n` starts a second instance of Chrome so the page can have its own profile. That instance has no Dock
icon of its own, and Chrome writes the window's frame into the profile and puts it back there next time,
including onto a monitor that is no longer plugged in. Minimized, or left on that monitor, there is nothing
to click, which is why the window seemed gone until `make restart` launched Chrome again.

Coordinates here are Chrome's and CoreGraphics': origin at the top-left of the main display, y downward.
"""

from __future__ import annotations

import ctypes
import fcntl
import json
import logging
import os
import plistlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MARGIN = 48  # pixels still on a display before a window counts as something you can grab
WATCH_EVERY = 2.0
_DEBOUNCE = 2  # ticks; macOS is often still moving the window for a moment after a display goes away
_COOLING = 12.0
_ICON = Path(__file__).parent / "static" / "codepilot.icns"
_BUNDLE = "dev.codepilot.app"


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Frame:
    """One of the app browser's windows. `onscreen` is false when it's minimized."""

    bounds: Rect
    onscreen: bool


def new_state() -> dict:
    return {"key": None, "ticks": 0, "attempts": 0, "until": 0.0, "pending": False}


def overlaps(window: Rect, screens: Sequence[Rect], margin: int = MARGIN) -> bool:
    """True when enough of the window lies on one of these displays to grab it."""
    if window.w <= 0 or window.h <= 0:
        return False
    need = min(margin, window.w, window.h)
    for screen in screens:
        width = min(window.x + window.w, screen.x + screen.w) - max(window.x, screen.x)
        height = min(window.y + window.h, screen.y + screen.h) - max(window.y, screen.y)
        if width >= need and height >= need:
            return True
    return False


def fit(bounds: Rect, screen: Rect) -> Rect:
    """`bounds` moved onto `screen`, shrunk if it couldn't fit, otherwise at its own size."""
    width = min(bounds.w, screen.w)
    height = min(bounds.h, screen.h)
    inside = (bounds.x >= screen.x and bounds.y >= screen.y
              and bounds.x + width <= screen.x + screen.w and bounds.y + height <= screen.y + screen.h)
    if inside:
        return Rect(bounds.x, bounds.y, width, height)
    return Rect(screen.x, screen.y, width, height)


def _placement_bounds(node: dict) -> Rect | None:
    keys = ("left", "top", "right", "bottom")
    if not all(isinstance(node.get(key), (int, float)) for key in keys):
        return None
    width = int(node["right"]) - int(node["left"])
    height = int(node["bottom"]) - int(node["top"])
    if width <= 0 or height <= 0:
        return None
    return Rect(int(node["left"]), int(node["top"]), width, height)


def _clamp_tree(node: dict, screens: Sequence[Rect], home: Rect) -> bool:
    bounds = _placement_bounds(node)
    if bounds is not None:
        if overlaps(bounds, screens):
            return False
        fitted = fit(bounds, home)
        node["left"], node["top"] = fitted.x, fitted.y
        node["right"], node["bottom"] = fitted.x + fitted.w, fitted.y + fitted.h
        node["work_area_left"], node["work_area_top"] = home.x, home.y
        node["work_area_right"], node["work_area_bottom"] = home.x + home.w, home.y + home.h
        node["maximized"] = False
        if "minimized" in node:
            node["minimized"] = False
        return True
    changed = False
    for value in node.values():
        if isinstance(value, dict):
            changed = _clamp_tree(value, screens, home) or changed
    return changed


def clamp_preferences(data: dict, screens: Sequence[Rect], home: Rect) -> bool:
    """Move saved frames that miss every display onto `home`. Returns whether anything changed.

    Chrome saves an --app window under its name, and a name like `127.0.0.1_/` is stored as nested dicts
    because a preference path splits on dots. Walk whatever shape that produced."""
    browser = data.get("browser")
    if not isinstance(browser, dict) or not screens:
        return False
    changed = False
    for key in ("app_window_placement", "window_placement"):
        node = browser.get(key)
        if isinstance(node, dict):
            changed = _clamp_tree(node, screens, home) or changed
    return changed


def _visible(frames: Sequence[Frame], screens: Sequence[Rect]) -> bool:
    return any(frame.onscreen and overlaps(frame.bounds, screens) for frame in frames)


def _parked(frames: Sequence[Frame], screens: Sequence[Rect]) -> list[Frame]:
    """Minimized (or otherwise not on screen) but its frame is still on a display that is plugged in."""
    return [frame for frame in frames if not frame.onscreen and overlaps(frame.bounds, screens)]


def _off(frames: Sequence[Frame], screens: Sequence[Rect]) -> list[Frame]:
    return [frame for frame in frames if not overlaps(frame.bounds, screens)]


def plan(frames: Sequence[Frame], screens: Sequence[Rect], saved: Rect | None, *, asked: bool,
         running: bool, home: Rect | None = None) -> tuple[str, Rect | None]:
    """What `codepilot start` should do. 'focus' launches as usual; 'relaunch' quits the profile's browser
    first and opens at the returned frame, which also clears a minimized window."""
    del asked, running
    home = home or (screens[0] if screens else None)
    if not screens or home is None:
        return "focus", None
    if _visible(frames, screens):
        return "focus", None
    parked = _parked(frames, screens)
    if parked:
        return "relaunch", fit(saved or parked[0].bounds, home)
    source = saved if saved is not None else (frames[0].bounds if frames else None)
    if source is None or overlaps(source, screens):
        return "focus", None
    return "relaunch", fit(source, home)


def watch_tick(state: dict, frames: Sequence[Frame], screens: Sequence[Rect], *, running: bool,
               now: float) -> str | None:
    """'relaunch' when the window has stayed off every plugged-in display, else leave it.

    One look isn't enough: just after a display is unplugged, macOS is often still moving the window, and
    relaunching then would throw away a window that was about to reappear. A minimized window whose frame
    is still on this display is left minimized; nothing you can click would pop it back on its own."""
    if not screens:
        return None
    key = tuple((screen.x, screen.y, screen.w, screen.h) for screen in screens)
    changed = state["key"] is not None and state["key"] != key
    state["key"] = key
    if changed:
        state["attempts"] = 0
    if _visible(frames, screens):
        state["attempts"] = 0
        state["ticks"] = 0
        state["pending"] = False
        return None
    if _parked(frames, screens):
        state["ticks"] = 0
        state["pending"] = False
        return None
    if not running:
        state["pending"] = False
        state["ticks"] = 0
        return None
    if changed:
        state["pending"] = True
    if not _off(frames, screens) and not state["pending"]:
        return None
    if now < state["until"]:
        return None
    state["ticks"] += 1
    if state["ticks"] < _DEBOUNCE:
        return None
    if state["attempts"] >= 1 and not changed:
        return None
    state["attempts"] += 1
    state["ticks"] = 0
    state["until"] = now + _COOLING
    state["pending"] = False
    return "relaunch"


def chrome_args(bounds: Rect) -> list[str]:
    """Flags Chrome applies after its saved frame, and that force the window out of the minimized state."""
    return [f"--window-position={bounds.x},{bounds.y}", f"--window-size={bounds.w},{bounds.h}"]


def _profile_in(command: str, profile: str) -> bool:
    needle = "--user-data-dir=" + profile
    start = 0
    while True:
        found = command.find(needle, start)
        if found < 0:
            return False
        after = found + len(needle)
        if after >= len(command) or command[after] in " \t":
            return True
        start = found + 1


def _pids(listing: str, profile: Path, *, main_only: bool) -> list[int]:
    want = str(profile)
    found = []
    for line in listing.splitlines():
        line = line.strip()
        if not line or not _profile_in(line, want):
            continue
        if main_only and "--type=" in line:  # renderers and gpu helpers die with the main process
            continue
        pid = line.split(None, 1)[0]
        if pid.isdigit():
            found.append(int(pid))
    return found


def main_pids(listing: str, profile: Path) -> list[int]:
    return _pids(listing, profile, main_only=True)


def profile_pids(listing: str, profile: Path) -> list[int]:
    return _pids(listing, profile, main_only=False)


def frames_for(records: Sequence[dict], pids: Sequence[int]) -> list[Frame]:
    want = set(pids)
    frames = []
    for record in records:
        if record.get("pid") not in want or record["w"] < 200 or record["h"] < 120:
            continue
        bounds = Rect(int(record["x"]), int(record["y"]), int(record["w"]), int(record["h"]))
        frames.append(Frame(bounds, bool(record["onscreen"])))
    return frames


def _enabled() -> bool:
    return os.environ.get("CODEPILOT_WINDOW_RECOVER", "1").strip() != "0"


def process_listing() -> str:
    try:
        return subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True,
                              timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def signal_pid(pid: int, sig: int) -> None:
    os.kill(pid, sig)


def quit_browser(pids: Sequence[int]) -> None:
    for pid in pids:
        try:
            signal_pid(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 4
    while time.time() < deadline and any(pid_alive(pid) for pid in pids):
        time.sleep(0.1)
    for pid in pids:
        if pid_alive(pid):
            try:
                signal_pid(pid, signal.SIGKILL)
            except OSError:
                pass
    time.sleep(0.2)  # the profile's singleton lock is released as the process exits


def _clear_singleton(profile: Path) -> None:
    """A lock left behind makes the next launch hand the new window to a browser that has already exited."""
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            (profile / name).unlink()
        except OSError:
            pass


def _coregraphics():
    return ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")


def _corefoundation():
    return ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")


def displays() -> list[Rect]:
    """Full frames of the displays plugged in now, main display first. Empty if they can't be read."""
    if sys.platform != "darwin":
        return []
    try:
        cg = _coregraphics()
        cg.CGGetActiveDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                               ctypes.POINTER(ctypes.c_uint32)]
        cg.CGGetActiveDisplayList.restype = ctypes.c_int32
        cg.CGMainDisplayID.restype = ctypes.c_uint32
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGDisplayBounds.restype = _CGRect
        count = ctypes.c_uint32()
        if cg.CGGetActiveDisplayList(0, None, ctypes.byref(count)) != 0 or not count.value:
            return []
        ids = (ctypes.c_uint32 * count.value)()
        if cg.CGGetActiveDisplayList(count.value, ids, ctypes.byref(count)) != 0:
            return []
        main = cg.CGMainDisplayID()
        ordered = [main] + [ids[i] for i in range(count.value) if ids[i] != main]
        frames = []
        for display in ordered:
            rect = cg.CGDisplayBounds(display)
            frames.append(Rect(int(rect.origin.x), int(rect.origin.y), int(rect.size.width), int(rect.size.height)))
        return [frame for frame in frames if frame.w > 0 and frame.h > 0]
    except (OSError, AttributeError):
        return []


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


def window_records() -> list[dict]:
    """Every window's pid and frame. Off-screen windows are included; minimized ones say onscreen false."""
    if sys.platform != "darwin":
        return []
    try:
        return _window_records()
    except (OSError, AttributeError):
        return []


def _window_records() -> list[dict]:
    cg = _coregraphics()
    cf = _corefoundation()
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
    cf.CFBooleanGetValue.restype = ctypes.c_bool
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    encoding = 0x08000100  # kCFStringEncodingUTF8

    def cfstring(text: str):
        return cf.CFStringCreateWithCString(None, text.encode(), encoding)

    keys = {name: cfstring(name) for name in
            ("kCGWindowOwnerPID", "kCGWindowIsOnscreen", "kCGWindowBounds", "X", "Y", "Width", "Height")}
    array = cg.CGWindowListCopyWindowInfo(0, 0)  # every window, including ones off the current displays
    if not array:
        return []
    try:
        records = []
        for index in range(cf.CFArrayGetCount(array)):
            info = cf.CFArrayGetValueAtIndex(array, index)
            bounds = cf.CFDictionaryGetValue(info, keys["kCGWindowBounds"])
            pid_value = cf.CFDictionaryGetValue(info, keys["kCGWindowOwnerPID"])
            if not bounds or not pid_value:
                continue

            def number(ref, key, _bounds=bounds):
                value = cf.CFDictionaryGetValue(_bounds, keys[key])
                if not value:
                    return 0.0
                out = ctypes.c_double()
                cf.CFNumberGetValue(value, 13, ctypes.byref(out))  # kCFNumberDoubleType
                return out.value

            pid = ctypes.c_int()
            cf.CFNumberGetValue(pid_value, 9, ctypes.byref(pid))  # kCFNumberIntType
            onscreen = cf.CFDictionaryGetValue(info, keys["kCGWindowIsOnscreen"])
            records.append({"pid": pid.value, "x": number(bounds, "X"), "y": number(bounds, "Y"),
                            "w": number(bounds, "Width"), "h": number(bounds, "Height"),
                            "onscreen": bool(cf.CFBooleanGetValue(onscreen)) if onscreen else False})
        return records
    finally:
        cf.CFRelease(array)
        for key in keys.values():
            cf.CFRelease(key)


_WORK_AREA_SCRIPT = """
ObjC.import("AppKit");
const screens = $.NSScreen.screens;
if (!screens || screens.count < 1) {
  JSON.stringify(null);
} else {
  const screen = screens.objectAtIndex(0);
  const frame = screen.frame;
  const visible = screen.visibleFrame;
  const flip = frame.origin.y + frame.size.height;
  JSON.stringify({x: visible.origin.x, y: flip - (visible.origin.y + visible.size.height),
                  w: visible.size.width, h: visible.size.height});
}
"""


def work_area() -> Rect | None:
    """The main display's visible frame (below the menu bar, above the Dock), in Chrome's coordinates."""
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["osascript", "-l", "JavaScript", "-e", _WORK_AREA_SCRIPT],
                             capture_output=True, text=True, timeout=4)
        data = json.loads(out.stdout or "null")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    width, height = int(data.get("w", 0)), int(data.get("h", 0))
    if width < 400 or height < 300:
        return None
    return Rect(int(data["x"]), int(data["y"]), width, height)


def _inset(screen: Rect) -> Rect:
    """A frame clear of a menu bar and a Dock, when AppKit can't be asked."""
    top, dock = 25, 70
    return Rect(screen.x, screen.y + top, screen.w, max(400, screen.h - top - dock))


def _saved_bounds(profile: Path) -> Rect | None:
    try:
        data = json.loads((profile / "Default" / "Preferences").read_text())
    except (OSError, ValueError):
        return None
    found: list[Rect] = []

    def walk(node: dict) -> None:
        bounds = _placement_bounds(node)
        if bounds is not None:
            found.append(bounds)
            return
        for value in node.values():
            if isinstance(value, dict):
                walk(value)

    browser = data.get("browser")
    if isinstance(browser, dict):
        for key in ("app_window_placement", "window_placement"):
            node = browser.get(key)
            if isinstance(node, dict):
                walk(node)
    return found[0] if found else None


def clamp_profile(profile: Path, screens: Sequence[Rect], home: Rect) -> None:
    path = profile / "Default" / "Preferences"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return
    if not clamp_preferences(data, screens, home):
        return
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def inspect(profile: Path) -> tuple[list[Frame], bool, list[int]]:
    listing = process_listing()
    mains = main_pids(listing, profile)
    return frames_for(window_records(), profile_pids(listing, profile)), bool(mains), mains


def _source(frames: Sequence[Frame], screens: Sequence[Rect], profile: Path) -> Rect | None:
    for frame in frames:
        if not overlaps(frame.bounds, screens):
            return frame.bounds
    saved = _saved_bounds(profile)
    if saved is not None:
        return saved
    return frames[0].bounds if frames else None


@contextmanager
def _lock(profile: Path):
    path = profile.parent / "window.lock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a")
    except OSError:
        yield False
        return
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def recover(profile: Path, *, asked: bool, state: dict | None = None) -> list[str] | None:
    """Extra Chrome arguments so the next launch is on a plugged-in display.

    `asked` is `codepilot start` or a Dock click: a minimized window is opened again. Otherwise this is the
    background check, which only acts once a window has stayed off every display, and returns None to mean
    "do nothing". `[]` means launch as usual."""
    if not _enabled():
        return [] if asked else None
    if sys.platform != "darwin":
        return [] if asked else None
    try:
        return _recover(profile, asked=asked, state=state)
    except Exception:
        log.exception("couldn't place the app window")
        return [] if asked else None


def _recover(profile: Path, *, asked: bool, state: dict | None) -> list[str] | None:
    screens = displays()
    if not screens:
        return [] if asked else None
    with _lock(profile) as got:
        if not got:
            return [] if asked else None
        frames, running, mains = inspect(profile)
        if not asked:
            if watch_tick(state if state is not None else new_state(), frames, screens,
                          running=running, now=time.time()) != "relaunch":
                return None
        elif _visible(frames, screens):
            return []  # already on a display; the launch below just brings it forward
        home = work_area() or _inset(screens[0])
        if not asked:
            source = _source(frames, screens, profile) or home
            if running:
                quit_browser(mains)
            _clear_singleton(profile)
            clamp_profile(profile, screens, home)
            log.info("The app window was off screen; opening it on this display.")
            return chrome_args(fit(source, home))
        action, bounds = plan(frames, screens, _source(frames, screens, profile), asked=True, running=running,
                              home=home)
        if action != "relaunch" or bounds is None:
            return []
        if running:
            quit_browser(mains)
        _clear_singleton(profile)
        clamp_profile(profile, screens, home)
        if _parked(frames, screens):
            log.info("The app window was minimized; opening it again.")
        else:
            log.info("The app window was off screen; opening it on this display.")
        return chrome_args(bounds)


def watch(profile: Path, launch: Callable[[list[str]], None]) -> Callable[[], None]:
    """Start the background check. Returns a function that stops it. No-op when recovery is off."""
    if not _enabled() or sys.platform != "darwin":
        return lambda: None
    stop = threading.Event()
    state = new_state()

    def loop() -> None:
        while not stop.wait(WATCH_EVERY):
            try:
                extra = recover(profile, asked=False, state=state)
                if extra is not None:
                    launch(extra)
            except Exception:
                log.exception("couldn't check the app window")

    threading.Thread(target=loop, name="codepilot-window", daemon=True).start()
    return stop.set


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dock_source(python: str, env_path: Path | None, log_path: Path) -> str:
    """A stay-open Dock app: clicking it runs `codepilot start`, which opens the window again."""
    parts = [python, "-m", "codepilot"]
    if env_path:
        parts += ["--env-file", str(env_path)]
    parts.append("start")
    shell = (f"mkdir -p {shlex.quote(str(log_path.parent))} && nohup {' '.join(shlex.quote(part) for part in parts)}"
             f" >> {shlex.quote(str(log_path))} 2>&1 &")
    line = f"do shell script {_applescript_string(shell)}"
    return f"on run\n  {line}\nend run\non reopen\n  {line}\nend reopen\n"


def write_dock_app(dest: Path, python: str, env_path: Path | None, log_path: Path,
                   icon: Path | None = None) -> None:
    """Build a stay-open Codepilot.app. An older launcher (a shell script that exits) is replaced.

    Compiled into a temporary folder first, and only swapped into place if that succeeds, so a failed
    build doesn't remove the app you already have. osacompile only builds a bundle when the name ends in .app."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = dock_source(python, env_path, log_path)
    script = dest.parent / f".{dest.name}.applescript"
    script.write_text(source)
    try:
        with tempfile.TemporaryDirectory(prefix=".codepilot-app-", dir=dest.parent) as tmp:
            staging = Path(tmp) / "Codepilot.app"
            subprocess.run(["osacompile", "-s", "-o", str(staging), str(script)], check=True,
                           capture_output=True, text=True)
            icon_path = icon or _ICON
            resources = staging / "Contents" / "Resources"
            if icon_path.is_file():
                shutil.copy(icon_path, resources / "codepilot.icns")
            (resources / "Scripts").mkdir(parents=True, exist_ok=True)
            (resources / "Scripts" / "main.applescript").write_text(source)
            plist_path = staging / "Contents" / "Info.plist"
            with open(plist_path, "rb") as handle:
                plist = plistlib.load(handle)
            for key in [key for key in plist if key.startswith("NS") and key.endswith("UsageDescription")]:
                del plist[key]  # osacompile lists the camera, contacts and the rest, which this app never uses
            plist.pop("LSUIElement", None)  # a Dock icon is how a minimized window gets opened again
            plist.update({"CFBundleName": "Codepilot", "CFBundleDisplayName": "Codepilot",
                          "CFBundleIdentifier": _BUNDLE, "CFBundleIconFile": "codepilot",
                          "CFBundleShortVersionString": "1.0", "OSAAppletStayOpen": True})
            with open(plist_path, "wb") as handle:
                plistlib.dump(plist, handle)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(staging), str(dest))
    finally:
        script.unlink(missing_ok=True)
    subprocess.run(["touch", str(dest)], check=False)


def _plist(app: Path) -> dict | None:
    try:
        with open(app / "Contents" / "Info.plist", "rb") as handle:
            return plistlib.load(handle)
    except (OSError, ValueError):
        return None


def _stay_open(app: Path) -> bool:
    plist = _plist(app)
    return bool(plist and plist.get("OSAAppletStayOpen"))


def _is_our_app(app: Path) -> bool:
    plist = _plist(app)
    return bool(plist and plist.get("CFBundleIdentifier") == _BUNDLE)


def dock_running(app: Path) -> bool:
    try:
        needle = re.escape(str(app / "Contents" / "MacOS" / "applet"))
        return subprocess.run(["pgrep", "-f", needle], capture_output=True).returncode == 0
    except OSError:
        return False


def ensure_dock(home: Path, python: str, env_path: Path | None, applications: Path | None = None) -> None:
    """Leave Codepilot in the Dock, creating the app first if `codepilot app` hasn't been run."""
    applications = applications or (Path.home() / "Applications")
    installed = applications / "Codepilot.app"
    if _is_our_app(installed):
        app = installed
        if not _stay_open(app):
            write_dock_app(app, python, env_path, home / "launcher.log")
    else:
        app = home / "Codepilot.app"
        if not _stay_open(app):
            write_dock_app(app, python, env_path, home / "launcher.log")
    if not dock_running(app):
        subprocess.Popen(["open", "-a", str(app)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
