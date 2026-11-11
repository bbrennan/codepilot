"""The macOS app window stays on a display that is plugged in.

Chrome remembers an --app window's frame and puts it back there, including onto a monitor that is gone, and the
second Chrome instance `open -n` starts has no Dock icon of its own. Minimized or left on that monitor, the window
is unreachable until something launches Chrome again, which is all `make restart` was doing.
"""

import json
from pathlib import Path

from codepilot import service, window
from codepilot.window import Frame, Rect

LAPTOP = Rect(0, 0, 1680, 1050)
LAPTOP_WORK = Rect(0, 25, 1680, 956)  # below the menu bar, above the Dock
EXTERNAL = Rect(1680, 0, 1440, 900)
ON = Frame(Rect(80, 40, 1200, 800), True)
OFF = Frame(Rect(1800, 40, 1200, 800), True)  # still "on screen" to the window server, on a display that is gone
MINIMIZED = Frame(Rect(80, 40, 1200, 800), False)


def test_a_frame_saved_on_an_unplugged_display_moves_onto_the_laptop():
    # Chrome stores the app name `127.0.0.1_/` as nested dicts, because a preference path splits on dots.
    data = {"browser": {"app_window_placement": {"127": {"0": {"0": {"1_/": {
        "left": 1800, "top": 40, "right": 3000, "bottom": 840, "maximized": True,
        "work_area_left": 1680, "work_area_top": 0, "work_area_right": 3120, "work_area_bottom": 900,
    }}}}}}}
    assert window.clamp_preferences(data, [LAPTOP], LAPTOP_WORK)
    saved = data["browser"]["app_window_placement"]["127"]["0"]["0"]["1_/"]
    assert saved["left"] == 0 and saved["top"] == 25
    assert saved["right"] - saved["left"] == 1200 and saved["bottom"] - saved["top"] == 800
    assert saved["maximized"] is False
    assert saved["work_area_left"] == 0 and saved["work_area_right"] == 1680


def test_a_frame_already_on_this_display_is_left_alone():
    data = {"browser": {"window_placement": {
        "left": 0, "top": 25, "right": 1680, "bottom": 981, "maximized": False,
    }}}
    assert window.clamp_preferences(data, [LAPTOP], LAPTOP_WORK) is False
    assert data["browser"]["window_placement"]["left"] == 0


def test_a_window_bigger_than_the_laptop_shrinks_to_fit():
    assert window.fit(Rect(1800, 0, 2560, 1440), LAPTOP_WORK) == LAPTOP_WORK


def test_start_leaves_a_visible_window_where_it_is():
    assert window.plan([ON], [LAPTOP], ON.bounds, asked=True, running=True) == ("focus", None)


def test_start_reopens_a_minimized_window_where_it_was():
    # Minimized, its frame is still on this display, but the second Chrome instance has nothing to click.
    action, bounds = window.plan([MINIMIZED], [LAPTOP], MINIMIZED.bounds, asked=True, running=True)
    assert action == "relaunch" and bounds == MINIMIZED.bounds


def test_start_moves_a_window_left_on_the_unplugged_display():
    action, bounds = window.plan([OFF], [LAPTOP], OFF.bounds, asked=True, running=True, home=LAPTOP_WORK)
    assert action == "relaunch"
    assert bounds == Rect(0, 25, 1200, 800)


def test_a_fresh_start_lets_chrome_choose_a_spot():
    assert window.plan([], [LAPTOP], None, asked=True, running=False) == ("focus", None)


def test_unplugging_waits_to_see_the_window_stay_lost_then_brings_it_back_once():
    state = window.new_state()
    assert window.watch_tick(state, [ON], [LAPTOP, EXTERNAL], running=True, now=0) is None
    assert window.watch_tick(state, [OFF], [LAPTOP], running=True, now=2) is None  # macOS may still be moving it
    assert window.watch_tick(state, [OFF], [LAPTOP], running=True, now=4) == "relaunch"
    assert window.watch_tick(state, [OFF], [LAPTOP], running=True, now=30) is None  # don't relaunch forever


def test_a_display_change_mac_recovers_from_is_left_alone():
    state = window.new_state()
    window.watch_tick(state, [ON], [LAPTOP, EXTERNAL], running=True, now=0)
    assert window.watch_tick(state, [OFF], [LAPTOP], running=True, now=2) is None
    assert window.watch_tick(state, [ON], [LAPTOP], running=True, now=4) is None


def test_minimizing_on_this_display_does_not_pop_the_window_back():
    state = window.new_state()
    window.watch_tick(state, [ON], [LAPTOP], running=True, now=0)
    assert window.watch_tick(state, [MINIMIZED], [LAPTOP], running=True, now=2) is None
    assert window.watch_tick(state, [MINIMIZED], [LAPTOP], running=True, now=4) is None


def test_closing_the_window_does_not_open_another():
    state = window.new_state()
    window.watch_tick(state, [ON], [LAPTOP], running=True, now=0)
    assert window.watch_tick(state, [], [LAPTOP], running=False, now=2) is None
    assert window.watch_tick(state, [], [LAPTOP], running=False, now=4) is None


def test_only_the_main_chrome_process_for_this_profile_is_the_one_to_quit():
    profile = "/tmp/codepilot-chrome"
    listing = "\n".join([
        f"10 /Chrome --app=http://127.0.0.1:8765 --user-data-dir={profile} --no-first-run",
        f"11 /Chrome --type=renderer --user-data-dir={profile}",
        "12 /Chrome --user-data-dir=/Users/me/Library/Application Support/Google/Chrome",
        f"13 /Chrome --user-data-dir={profile}-other",
    ])
    assert window.main_pids(listing, Path(profile)) == [10]
    assert window.profile_pids(listing, Path(profile)) == [10, 11]


def test_a_lost_window_is_quit_and_reopened_on_the_laptop(tmp_path, monkeypatch):
    profile = tmp_path / "chrome"
    prefs = profile / "Default" / "Preferences"
    prefs.parent.mkdir(parents=True)
    prefs.write_text(json.dumps({"browser": {"app_window_placement": {"127": {"0": {"0": {"1_/": {
        "left": 1800, "top": 40, "right": 2600, "bottom": 840, "maximized": False,
        "work_area_left": 1680, "work_area_top": 0, "work_area_right": 3120, "work_area_bottom": 900,
    }}}}}}}))
    monkeypatch.setattr(window.sys, "platform", "darwin")
    monkeypatch.setattr(window, "displays", lambda: [LAPTOP])
    monkeypatch.setattr(window, "work_area", lambda: LAPTOP_WORK)
    monkeypatch.setattr(window, "process_listing", lambda: f"10 /Chrome --user-data-dir={profile}\n")
    monkeypatch.setattr(window, "window_records", lambda: [
        {"pid": 10, "x": 1800, "y": 40, "w": 800, "h": 800, "onscreen": True}])
    killed = []
    monkeypatch.setattr(window, "signal_pid", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(window, "pid_alive", lambda pid: False)
    monkeypatch.setattr(window.time, "sleep", lambda _s: None)
    args = window.recover(profile, asked=True)
    assert killed == [10]
    assert "--window-position=0,25" in args and "--window-size=800,800" in args
    saved = json.loads(prefs.read_text())["browser"]["app_window_placement"]["127"]["0"]["0"]["1_/"]
    assert saved["left"] == 0 and saved["top"] == 25


def test_window_recover_0_leaves_chrome_alone(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEPILOT_WINDOW_RECOVER", "0")
    monkeypatch.setattr(window, "displays", lambda: (_ for _ in ()).throw(AssertionError("should not look")))
    assert window.recover(tmp_path, asked=True) == []
    assert window.recover(tmp_path, asked=False) is None


def test_the_app_window_opens_where_recover_says(monkeypatch):
    calls = []
    monkeypatch.setattr(service.sys, "platform", "darwin")
    monkeypatch.setattr(service.subprocess, "run", lambda argv, **kw: type("Done", (), {"returncode": 0})())
    monkeypatch.setattr(service.subprocess, "Popen", lambda argv, **kw: calls.append(argv))
    monkeypatch.setattr(window, "recover", lambda profile, asked: ["--window-position=0,25", "--window-size=800,600"])
    service.open_window("http://127.0.0.1:8765", profile=Path("/tmp/chrome"))
    argv = calls[0]
    assert "--window-position=0,25" in argv and "--window-size=800,600" in argv
    assert "--user-data-dir=/tmp/chrome" in argv


def test_the_dock_app_brings_the_window_back_when_clicked():
    src = window.dock_source("/usr/bin/python3", Path("/tmp/work.env"), Path("/tmp/launcher.log"))
    assert "on reopen" in src and "on run" in src
    assert "nohup" in src and "/usr/bin/python3" in src and "/tmp/work.env" in src and "start" in src


def test_ensure_dock_opens_the_app_when_it_is_not_running(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "write_dock_app", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "dock_running", lambda app: False)
    monkeypatch.setattr(window.subprocess, "Popen", lambda argv, **kw: opened.append(argv))
    window.ensure_dock(tmp_path, "/usr/bin/python3", None, applications=tmp_path / "Applications")
    assert opened and opened[0][:2] == ["open", "-a"]
    assert str(opened[0][2]).endswith("Codepilot.app")
