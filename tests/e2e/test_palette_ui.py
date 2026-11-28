"""Go anywhere from ⌘P (spec go-anywhere): it starts from the files you were in, takes `name:line` and `:line`, lists
commands after `>` (⇧⌘P), and finds sessions."""

import json
import time

from test_multi_folder_ui import api_folder
from test_restore_tabs_ui import lib_session, long_file, switch
from uihelpers import SCROLLER, editor_caret_line, editor_text, focus_editor, open_app, set_editor_text, wait_editor

ACTIVE = "() => document.querySelector('#editorTabs .tab.on')?.dataset.tab"


def open_palette(page, text="", keys="ControlOrMeta+p"):
    page.keyboard.press(keys)
    page.locator("#palette").wait_for()
    if text:
        page.keyboard.type(text)


def listed(page, text=None):
    """The options' titles once the list answers `text` (default: what's in the box), in order."""
    text = page.input_value("#paletteInput") if text is None else text
    page.wait_for_function("(t) => pal.shown === t", arg=text)
    return page.locator("#paletteList [role=option] .n").all_text_contents()


def open_files(page, *paths):
    for p in paths:
        page.evaluate("(p) => openFile(p)", p)
        page.wait_for_function("(p) => state.active === 'file:' + p", arg=p)


def active(page):
    return page.evaluate(ACTIVE)


# -- task 2: recent files and name:line --------------------------------------------------------------------------


def test_an_empty_palette_lists_the_files_you_were_in_with_the_one_before_on_top(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py", "tests/test_core.py", "Makefile")
    open_palette(page)
    assert listed(page, "") == ["test_core.py", "core.py"]  # (Makefile is the one shown)
    assert page.text_content("#paletteList .pal-head") == "Recently opened"
    page.keyboard.press("Enter")
    page.wait_for_function("() => state.active === 'file:tests/test_core.py'")
    open_palette(page)  # ⌘P, Enter: back and forth between two files
    assert listed(page, "") == ["Makefile", "core.py"]
    page.keyboard.press("Enter")
    page.wait_for_function("() => state.active === 'file:Makefile'")


def test_the_current_option_is_the_boxs_active_descendant(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py", "tests/test_core.py", "Makefile")
    open_palette(page)
    listed(page, "")
    box = page.locator("#paletteInput")
    assert box.get_attribute("role") == "combobox" and box.get_attribute("aria-controls") == "paletteList"
    assert page.get_attribute("#paletteList", "role") == "listbox"
    first = page.locator("#paletteList [role=option]").first
    assert box.get_attribute("aria-activedescendant") == first.get_attribute("id")
    assert first.get_attribute("aria-selected") == "true"
    page.keyboard.press("ArrowDown")
    second = page.locator("#paletteList [role=option]").nth(1)
    assert box.get_attribute("aria-activedescendant") == second.get_attribute("id")
    assert second.get_attribute("aria-selected") == "true" and first.get_attribute("aria-selected") == "false"
    head = page.locator("#paletteList .pal-head")  # a heading names its group and isn't an option
    assert head.get_attribute("role") != "option"
    assert page.locator("#paletteList [role=group]").get_attribute("aria-labelledby") == head.get_attribute("id")


def test_a_recent_file_deleted_on_disk_isnt_listed(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py", "tests/test_core.py", "Makefile")
    (server.repo / "agent" / "core.py").unlink()
    open_palette(page)
    assert listed(page, "") == ["test_core.py"]


def test_recent_files_survive_a_reload(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py", "Makefile")
    page.reload()
    page.locator("#tree [data-file]").first.wait_for()
    page.wait_for_function("() => state.active === 'file:Makefile'")  # (tabstate.js: the tabs came back)
    open_palette(page)
    assert listed(page, "") == ["core.py"]


def test_each_folder_has_its_own_recent_files(page, server, session, tmp_path):
    other = lib_session(server, tmp_path, session)
    open_app(page)
    open_files(page, "agent/core.py", "Makefile")
    switch(page, other.id)
    page.locator("#tree [data-dir='pkg']").wait_for()
    open_palette(page)
    assert "core.py" not in listed(page, "")  # (lib has none of its own yet)
    page.keyboard.press("Escape")
    (tmp_path / "lib" / "pkg" / "two.py").write_text("TWO = 2\n")
    open_files(page, "pkg/mod.py", "pkg/two.py")
    open_palette(page)
    assert listed(page, "") == ["mod.py"]
    page.keyboard.press("Escape")
    switch(page, session.id)
    page.wait_for_function("() => state.active === 'file:Makefile'")
    open_palette(page)
    assert listed(page, "") == ["core.py"]


def test_redrawing_the_same_file_writes_nothing(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py")
    page.evaluate("""() => { window.__writes = 0; const set = Storage.prototype.setItem;
      Storage.prototype.setItem = function (k, v) { if (k.startsWith('cp-recent:')) window.__writes++; return set.call(this, k, v); }; }""")
    page.evaluate("() => { for (let i = 0; i < 5; i++) renderEditor(); }")
    assert page.evaluate("window.__writes") == 0
    open_files(page, "Makefile")
    assert page.evaluate("window.__writes") == 1


def plant(page, records):
    page.add_init_script(f"""if (!sessionStorage.getItem('planted')) {{ sessionStorage.setItem('planted', '1');
      for (const [k, v] of Object.entries({json.dumps(records)})) localStorage.setItem(k, JSON.stringify(v)); }}""")


def recent_keys(page):
    return page.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('cp-recent:'))")


def test_recent_files_of_folders_not_opened_for_30_days_are_removed(page, server, session):
    now = time.time()
    plant(page, {"cp-recent:/old/folder": {"v": 1, "at": now - 31 * 86400, "paths": ["a.py"]},
                 "cp-recent:/recent/folder": {"v": 1, "at": now - 29 * 86400, "paths": ["a.py"]}})
    open_app(page)
    open_files(page, "agent/core.py")
    keys = recent_keys(page)
    assert "cp-recent:/old/folder" not in keys
    assert "cp-recent:/recent/folder" in keys and f"cp-recent:{server.repo}" in keys


def test_only_the_20_most_recent_folders_keep_their_recent_files(page, server, session):
    now = time.time()
    plant(page, {f"cp-recent:/f{i}": {"v": 1, "at": now - 3600 - i * 60, "paths": []} for i in range(20)})
    open_app(page)
    open_files(page, "agent/core.py")  # this folder is the newest of 21
    keys = recent_keys(page)
    assert f"cp-recent:{server.repo}" in keys and "cp-recent:/f18" in keys and "cp-recent:/f19" not in keys


def test_a_recent_file_in_an_added_folder_opens_or_is_left_out(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    open_files(page, f"{api}/src/app.py", "Makefile")
    open_palette(page)
    assert listed(page, "") == ["app.py"]
    assert page.text_content("#paletteList [role=option] .dir") == "api/src"
    page.keyboard.press("Enter")
    page.locator("#editor code", has_text="PORT = 8000").wait_for()
    open_files(page, "Makefile")
    server.store.update_session(session.id, folders=[])  # the folder is taken out of the session
    page.reload()
    page.wait_for_function("() => state.active === 'file:Makefile'")
    open_palette(page)
    shown = listed(page, "")  # left out, with no error: nothing recent to show, so the folder's files
    assert "app.py" not in shown and "core.py" in shown


def test_name_colon_line_opens_the_file_at_that_line(page, server, session):
    long_file(server, lines=80)
    open_app(page)
    open_palette(page, "long.py:40")
    assert listed(page) == ["long.py"]
    page.keyboard.press("Enter")
    page.wait_for_function("() => state.active === 'file:long.py'")
    assert page.evaluate("() => state.tabs.find((t) => t.id === state.active).flash") == 40
    page.locator("#editor .line-hl.flash").wait_for()


def test_colon_line_goes_to_a_line_in_the_file_shown(page, server, session):
    long_file(server, lines=300)
    open_app(page)
    open_files(page, "long.py")
    open_palette(page, ":60")
    assert listed(page) == ["Go to line 60 in long.py"]
    page.keyboard.press("Enter")
    page.wait_for_function("() => state.tabs.find((t) => t.id === state.active).flash === 60")
    assert page.evaluate("() => state.tabs.find((t) => t.id === state.active).topLine") == 53  # (place.js: jumpTop)


def test_colon_line_with_no_file_shown_lists_nothing(page, server, session):
    open_app(page)
    open_palette(page, ":5")
    assert listed(page) == []
    assert "Open a file" in page.text_content("#paletteList")
    page.keyboard.press("Enter")  # nothing to take
    assert page.is_visible("#palette")


def test_a_line_in_a_file_being_edited_moves_the_caret_and_keeps_the_draft(page, server, session):
    long_file(server, lines=80)
    open_app(page)
    open_files(page, "long.py")
    page.click("#fEdit")
    draft = "# mine\n" + editor_text(page)
    set_editor_text(page, draft)
    page.wait_for_function("() => state.tabs.find((t) => t.id === state.active).dirty")
    open_palette(page, ":50")
    assert listed(page) == ["Go to line 50 in long.py"]
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelector('#palette').hidden")
    assert editor_caret_line(page) == 50
    assert editor_text(page) == draft
    page.wait_for_function("() => codeEditor().owns(document.activeElement)")  # where you can type at it
    page.wait_for_function(f"""() => {{ const s = ({SCROLLER})(document.querySelector('#codeEdit'));
      const top = Math.floor(s.scrollTop / 20) + 1; return top <= 50 && 50 < top + Math.floor(s.clientHeight / 20); }}""")
    open_palette(page, "long.py:20")  # the same, by name
    listed(page)
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelector('#palette').hidden")
    page.wait_for_function("() => codeEditor().text().slice(0, codeEditor().place().caret).split('\\n').length === 20")
    assert editor_text(page) == draft and active(page) == "file:long.py"


def test_go_to_line_on_the_editors_handle(page, server, session):
    long_file(server, lines=80)
    open_app(page)
    open_files(page, "long.py")
    page.click("#fEdit")
    wait_editor(page)
    set_editor_text(page, "# unsaved\n" + editor_text(page))
    page.evaluate("() => codeEditor().goToLine(70)")
    assert editor_caret_line(page) == 70
    assert editor_text(page).startswith("# unsaved\n")
    page.evaluate("() => codeEditor().goToLine(999)")  # past the end: the last line
    assert editor_caret_line(page) == page.evaluate("() => codeEditor().text().split('\\n').length")


def test_the_palette_opens_without_a_folder_and_says_to_open_one(page, server):
    server.store.create_session("", "main")
    open_app(page, wait_tree=False)
    page.wait_for_function("() => state.sid && state.workspace === ''")
    open_palette(page)
    assert listed(page, "") == []
    assert "Open a folder" in page.text_content("#paletteList")


# -- task 3: commands --------------------------------------------------------------------------------------------------

TABS = "() => [...document.querySelectorAll('#editorTabs .tab')].map((t) => t.dataset.tab)"
FIND = "#codeEdit input[aria-label='Find']"  # (test_code_editor_ui: the find panel by its box's name)
PANE = ".term-pane:not([hidden])"


def wait_closed(page):
    page.wait_for_function("() => document.querySelector('#palette').hidden")


def focus_is(page, sel):
    return page.evaluate("(s) => !!document.activeElement?.matches(s)", sel)


def key_label(page, combo):
    return page.evaluate("(c) => keyLabel(c)", combo)


def test_typed_words_find_a_command_with_its_shortcut_and_enter_runs_it(page, server, session):
    open_app(page)
    open_palette(page, ">tog side")
    assert listed(page) == ["Toggle sidebar"]
    assert page.text_content("#paletteList .opt.on kbd") == key_label(page, "mod+b")
    page.keyboard.press("Enter")
    wait_closed(page)
    assert not page.evaluate("layoutShown(ide, 'sidebar')")
    open_palette(page, ">SIDE Tog")  # any order, any case
    assert listed(page) == ["Toggle sidebar"]
    page.keyboard.press("Escape")
    open_palette(page, ">no such thing")
    assert listed(page) == [] and "No matching commands" in page.text_content("#paletteList")


def test_shortcuts_beside_commands_are_written_by_keyLabel(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py")
    open_palette(page, ">")
    listed(page)
    shown = dict(zip(page.locator("#paletteList [role=option]:has(kbd) .n").all_text_contents(),
                     page.locator("#paletteList [role=option] kbd").all_text_contents()))
    for title, combo in {"Toggle sidebar": "mod+b", "Toggle bottom panel": "mod+j", "Focus chat": "mod+l",
                         "Close Tab": "alt+w"}.items():
        assert shown[title] == key_label(page, combo), title


def test_shift_mod_p_opens_the_palette_on_commands(page, server, session):
    open_app(page)
    open_palette(page, keys="ControlOrMeta+Shift+p")
    assert page.input_value("#paletteInput") == ">"
    assert "Toggle sidebar" in listed(page, ">")
    page.keyboard.press("Escape")
    wait_closed(page)
    open_palette(page)  # ⌘P is still files
    assert page.input_value("#paletteInput") == ""


def test_shift_mod_p_works_from_the_editor_its_find_panel_and_the_terminal(page, server, session):
    page.add_init_script("localStorage.setItem('cp-no-panel', '0')")
    open_app(page)
    open_files(page, "agent/core.py")
    page.click("#fEdit")
    before = editor_text(page)
    focus_editor(page)
    open_palette(page, keys="ControlOrMeta+Shift+p")
    assert page.input_value("#paletteInput") == ">"
    page.keyboard.press("Escape")
    wait_closed(page)
    assert editor_text(page) == before
    focus_editor(page)
    page.keyboard.press("ControlOrMeta+f")
    page.locator(FIND).wait_for()
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=FIND)
    open_palette(page, keys="ControlOrMeta+Shift+p")
    assert page.input_value("#paletteInput") == ">"
    page.keyboard.press("Escape")
    wait_closed(page)
    page.evaluate("newTerminal()")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    page.wait_for_function("(p) => document.activeElement?.closest(p)", arg=PANE)
    open_palette(page, keys="ControlOrMeta+Shift+p")
    assert page.input_value("#paletteInput") == ">"
    assert editor_text(page) == before


def test_save_and_stop_are_listed_only_when_they_can_run(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py")
    open_palette(page, ">save")
    assert "Save" not in listed(page)
    page.keyboard.press("Escape")
    page.click("#fEdit")
    wait_editor(page)
    open_palette(page, ">save")
    assert "Save" in listed(page)
    assert page.text_content("#paletteList .opt.on kbd") == key_label(page, "mod+s")
    page.keyboard.press("Escape")
    open_palette(page, ">stop")
    assert "Stop" not in listed(page)
    page.keyboard.press("Escape")
    page.fill("#input", "very slow")
    page.press("#input", "Enter")
    page.locator("#stopBtn").wait_for()
    open_palette(page, ">stop")
    assert listed(page) == ["Stop"]
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def test_the_commands_cover_the_app(page, server, session):
    (server.repo / ".codepilot/modes").mkdir(parents=True)
    (server.repo / ".codepilot/modes/perf.md").write_text(
        "---\nname: perf\nlabel: Perf\ndescription: Find and fix performance problems\n---\nMeasure first.\n")
    server.store.add_proposal(session.id, "Makefile", "echo eval", "echo evaluate", "say more")
    open_app(page)
    open_files(page, "agent/core.py", "Makefile")
    open_palette(page, ">")
    titles = listed(page)
    views = page.evaluate("""() => [...document.querySelectorAll('#activitybar button[data-view]')]
      .filter((b) => !b.hidden).map((b) => 'Show ' + b.title.split(':')[0])""")
    modes = page.evaluate("() => state.wsInfo.modes.map((m) => 'Mode: ' + m.label)")
    assert "Mode: Perf" in modes  # (the folder's own mode, from its file)
    expected = ["Toggle sidebar", "Toggle bottom panel", "Toggle chat", "Toggle theme", *views,
                "Start a new session on this folder", "New File…", "New Folder…", "Add folder…", "New Terminal",
                "Close Tab", "Close other tabs", "Run tests", "Run checks", "Review changes", "Apply all changes",
                "Compact now", *modes, "Model: auto", "Model: fast", "Model: main", "Model: hard",
                "Report a problem", "Restart the codepilot server (loads updated code)"]
    assert [t for t in expected if t not in titles] == []
    assert len(titles) == len(set(titles)), "a command is listed twice"
    assert "Go to File…" not in titles  # (the File menu's way here)


def test_a_mode_and_a_model_from_the_palette(page, server, session):
    open_app(page)
    open_palette(page, ">mode ask")
    assert listed(page) == ["Mode: Ask"]
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelector('#modeSelect').value === 'ask'")
    open_palette(page, ">model hard")
    assert listed(page) == ["Model: hard"]
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelector('#tier').value === 'tier:hard'")


def test_a_script_adds_a_command_by_registering_it(page, server, session):
    open_app(page)
    page.evaluate("""registerCommand({ id: 'test.hello', title: 'Say hello', keys: 'mod+shift+h',
      run: () => toast('hello from a command') })""")
    open_palette(page, ">say hel")
    assert listed(page) == ["Say hello"]
    assert page.text_content("#paletteList .opt.on kbd") == key_label(page, "mod+shift+h")
    page.keyboard.press("Enter")
    page.locator(".toast", has_text="hello from a command").wait_for()
    page.evaluate("registerCommand({ id: 'test.later', title: 'Not yet', when: () => window.__ready, run: () => {} })")
    open_palette(page, ">not yet")
    assert listed(page) == []
    page.keyboard.press("Escape")
    page.evaluate("window.__ready = true")
    open_palette(page, ">not yet")
    assert listed(page) == ["Not yet"]


def test_new_file_from_the_palette_makes_one_file_and_the_palette_stays_shut(page, server, session):
    open_app(page)
    before = sorted(p.name for p in server.repo.iterdir())
    page.focus("#paletteBtn")  # opened from its button: where focus goes back to when the prompt closes
    page.keyboard.press("Enter")
    page.locator("#palette").wait_for()
    page.keyboard.type(">new file")
    assert listed(page)[0] == "New File…"
    page.keyboard.press("Enter")
    page.locator("#dialog").wait_for()
    page.wait_for_function("() => document.activeElement === document.querySelector('#dialogInput')")
    page.keyboard.type("notes.txt")
    page.keyboard.press("Enter")
    wait_editor(page)
    page.wait_for_function("() => codeEditor().owns(document.activeElement)")  # the new file, ready to type in
    page.wait_for_timeout(300)  # (anything that would go wrong after the key has had its chance)
    assert page.evaluate("() => document.querySelector('#palette').hidden && document.querySelector('#dialog').hidden")
    assert sorted(p.name for p in server.repo.iterdir()) == sorted([*before, "notes.txt"])
    assert page.evaluate("() => codeEditor().owns(document.activeElement)")


def test_focus_chat_from_the_palette_leaves_focus_in_the_message_box_with_nothing_typed(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py")
    open_palette(page, ">focus chat")
    assert listed(page) == ["Focus chat"]
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.activeElement === document.querySelector('#input')")
    page.wait_for_timeout(300)
    assert focus_is(page, "#input") and page.input_value("#input") == ""


def test_new_terminal_from_the_palette_ends_with_focus_in_the_terminal(page, server, session):
    page.add_init_script("localStorage.setItem('cp-no-panel', '0')")
    open_app(page)
    open_palette(page, ">new terminal")
    assert listed(page)[0] == "New Terminal"
    page.keyboard.press("Enter")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    page.wait_for_function("(p) => document.activeElement?.closest(p)", arg=PANE)
    page.wait_for_timeout(300)
    assert page.evaluate("(p) => !!document.activeElement?.closest(p)", PANE)


def test_close_other_tabs_asks_about_unsaved_ones_as_closing_one_does(page, server, session):
    open_app(page)
    open_files(page, "agent/core.py")
    page.click("#fEdit")
    set_editor_text(page, "# changed\n")
    page.wait_for_function("() => document.querySelector('.tab.on').classList.contains('dirty')")
    open_files(page, "tests/test_core.py", "Makefile")
    open_palette(page, ">close other")
    assert listed(page) == ["Close other tabs"]
    page.keyboard.press("Enter")
    page.locator("#dialog").wait_for()
    assert page.text_content("#dialogTitle") == "Discard changes to core.py?"
    page.click("#dialogCancel")
    page.wait_for_function(f"() => ({TABS})().join() === 'file:agent/core.py,file:Makefile'")
    open_palette(page, ">close other")
    listed(page)
    page.keyboard.press("Enter")
    page.locator("#dialog").wait_for()
    page.click("#dialogOk")
    page.wait_for_function(f"() => ({TABS})().join() === 'file:Makefile'")
    open_palette(page, ">close other")
    assert listed(page) == []  # one tab: nothing to close


def test_close_tab_closes_any_tab_once(page, server, session):
    server.store.add_proposal(session.id, "Makefile", "echo eval", "echo evaluate", "say more")
    open_app(page)
    open_files(page, "agent/core.py")
    open_palette(page, ">close tab")
    assert listed(page) == ["Close Tab"]  # (the File menu's, for a file)
    page.keyboard.press("Escape")
    page.evaluate("openReview()")
    page.wait_for_function("() => state.active === 'review'")
    open_palette(page, ">close tab")
    titles = listed(page)
    assert titles[0] == "Close Tab" and titles.count("Close Tab") == 1  # and for any other tab, as ⌥W
    assert page.text_content("#paletteList .opt.on kbd") == key_label(page, "alt+w")
    page.keyboard.press("Enter")
    page.wait_for_function(f"() => ({TABS})().join() === 'file:agent/core.py'")


# -- task 4: sessions and the placeholder ------------------------------------------------------------------------------


def group(page, heading):
    """The titles of the options under heading."""
    return page.locator(f"#paletteList [role=group]:has(> .pal-head:text-is('{heading}')) [role=option] .n") \
        .all_text_contents()


def test_typed_text_lists_matching_sessions_under_their_heading_and_enter_opens_one(page, server, session):
    found = server.store.create_session(str(server.repo), "main")
    server.store.update_session(found.id, title="export bug")
    other = server.store.create_session(str(server.repo), "main")
    server.store.update_session(other.id, title="hello")
    server.store.update_session(session.id, title="first")
    open_app(page)
    page.wait_for_function("() => (state.sessionList || []).length === 3")
    open_palette(page, "export")
    assert listed(page) == ["export bug"]  # (no file is called that)
    assert group(page, "Sessions") == ["export bug"]
    assert "No matching files." in page.text_content("#paletteList")
    page.keyboard.press("Enter")
    page.wait_for_function("(sid) => state.sid === sid", arg=found.id)
    page.wait_for_function("() => document.querySelector('#chatTitle').textContent === 'export bug'")


def test_sessions_come_after_the_files_and_are_five_at_most(page, server, session):
    for i in range(7):
        s = server.store.create_session(str(server.repo), "main")
        server.store.update_session(s.id, title=f"core work {i}")
    open_app(page)
    page.wait_for_function("() => (state.sessionList || []).length === 8")
    open_palette(page, "core")
    titles = listed(page)
    files, sessions = group(page, "Files"), group(page, "Sessions")
    assert "core.py" in files and len(sessions) == 5 and titles == files + sessions
    assert page.locator("#paletteList .pal-head").all_text_contents() == ["Files", "Sessions"]
    page.keyboard.press("Escape")
    open_palette(page, "target")  # the folder's name finds its sessions too
    listed(page)
    assert len(group(page, "Sessions")) == 5


def test_the_placeholder_says_what_can_be_typed(page, server, session):
    open_app(page)
    open_palette(page)
    placeholder = page.get_attribute("#paletteInput", "placeholder")
    assert placeholder.startswith("Go to file") and "> commands" in placeholder and ": line" in placeholder
    assert page.text_content("#paletteBtn").startswith("Search files")


def test_in_a_480px_window_a_title_keeps_one_line_and_its_description_gives_way(page, server, session):
    page.set_viewport_size({"width": 480, "height": 800})
    open_app(page, wait_tree=False)
    page.wait_for_function("() => state.workspace")
    open_palette(page, ">mode")
    assert "Mode: Spec" in listed(page)
    lines = page.evaluate("""() => [...document.querySelectorAll('#paletteList [role=option] .n')].map((n) => {
      const r = document.createRange(); r.selectNodeContents(n);
      return [n.textContent, new Set([...r.getClientRects()].map((b) => Math.round(b.top))).size,
              n.scrollWidth <= n.clientWidth]; })""")
    assert [t for t, n, _ in lines if n != 1] == []
    assert [t for t, _, whole in lines if not whole] == []  # and not cut short
    box = page.locator("#paletteList").bounding_box()
    for opt in page.locator("#paletteList [role=option]").all():
        b = opt.bounding_box()
        assert b["x"] >= box["x"] - 1 and b["x"] + b["width"] <= box["x"] + box["width"] + 1


def test_commands_without_a_folder(page, server):
    server.store.create_session("", "main")
    open_app(page, wait_tree=False)
    page.wait_for_function("() => state.sid && state.workspace === ''")
    open_palette(page, ">")
    titles = listed(page)
    assert "Toggle sidebar" in titles and "Start a new session on this folder" in titles
    assert "Run tests" not in titles and "Add folder…" not in titles
    page.keyboard.press("Escape")
    server.store.update_session(page.evaluate("state.sid"), title="no folder yet")
    page.evaluate("loadSessions()")
    open_palette(page, "yet")  # the files say to open a folder; sessions are still found
    listed(page)
    assert group(page, "Sessions") == ["no folder yet"] and "Open a folder" in page.text_content("#paletteList")
