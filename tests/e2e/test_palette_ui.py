"""Go anywhere from ⌘P (spec go-anywhere): it starts from the files you were in, takes `name:line` and `:line`, lists
commands after `>` (⇧⌘P), and finds sessions."""

import json
import time

from test_multi_folder_ui import api_folder
from test_restore_tabs_ui import lib_session, long_file, switch
from uihelpers import SCROLLER, editor_caret_line, editor_text, open_app, set_editor_text, wait_editor

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
