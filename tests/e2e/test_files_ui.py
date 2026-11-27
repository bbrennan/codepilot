"""File operations as a user does them: the File menu, explorer buttons, context menus, keys, the editor."""

import re

from uihelpers import open_app

def menu(page, label):
    page.locator("#ctxMenu .mi span", has_text=re.compile(f"^{re.escape(label)}$")).click()


def answer(page, text):
    page.locator("#dialog").wait_for()
    page.fill("#dialogInput", text)
    page.press("#dialogInput", "Enter")


def confirm(page):
    page.locator("#dialogOk").wait_for()
    page.click("#dialogOk")


def mod(page):
    return "Meta" if page.evaluate("navigator.platform").startswith("Mac") else "Control"


def test_new_file_from_the_file_menu_then_edit_and_save(page, server, session):
    open_app(page)
    page.click("#fileMenuBtn")
    menu(page, "New File…")
    answer(page, "pkg/util.py")
    target = server.repo / "pkg" / "util.py"
    page.locator("#codeEdit").wait_for()  # opens straight into the editor
    assert target.exists() and target.read_text() == ""
    page.locator("#tree [data-file='pkg/util.py']").wait_for()  # revealed in the explorer

    page.keyboard.type("x = 1\n")
    page.wait_for_function("() => document.querySelector('.tab.on').classList.contains('dirty')")
    page.keyboard.press(f"{mod(page)}+s")
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    assert target.read_text() == "x = 1\n"
    page.click("#fDone")
    page.locator("#editor code", has_text="x = 1").wait_for()


def test_new_folder_goes_in_the_selected_folder(page, server, session):
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.click("#newFolderBtn")
    answer(page, "helpers")
    page.locator("#tree [data-dir='agent/helpers']").wait_for()
    assert (server.repo / "agent" / "helpers").is_dir()
    page.click("#tree [data-dir='agent/helpers']")
    page.click("#newFileBtn")
    answer(page, "io.py")
    page.locator("#codeEdit").wait_for()
    assert (server.repo / "agent" / "helpers" / "io.py").exists()


def test_a_new_subfolder_shows_even_with_a_build_output_name(page, server, session):
    open_app(page)
    for name in ("build", "dist", "my notes"):  # build/dist used to be created but hidden from the explorer
        page.locator("#tree [data-dir='agent']").click(button="right")
        menu(page, "New Folder…")
        answer(page, name)
        page.locator(f"#tree [data-dir='agent/{name}']").wait_for()
        assert (server.repo / "agent" / name).is_dir()
    assert "dim" in page.get_attribute("#tree [data-dir='agent/build']", "class")
    assert "dim" not in page.get_attribute("#tree [data-dir='agent/my notes']", "class")


def test_existing_names_are_refused(page, server, session):
    page.expected_errors.append("409 (Conflict)")
    open_app(page)
    page.click("#newFileBtn")
    answer(page, "Makefile")
    page.get_by_text("Makefile already exists.").wait_for()
    assert (server.repo / "Makefile").read_text().startswith("eval-bedrock")


def test_rename_from_the_context_menu_keeps_open_tabs(page, server, session):
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.locator(".tab.on", has_text="core.py").wait_for()
    page.locator("#tree [data-file='agent/core.py']").click(button="right")
    menu(page, "Rename…")
    page.locator("#dialog").wait_for()
    assert page.input_value("#dialogInput") == "core.py"
    assert page.evaluate("[dialogInput.selectionStart, dialogInput.selectionEnd]") == [0, 4]  # the name, not ".py"
    page.keyboard.type("calc")
    page.keyboard.press("Enter")
    page.locator("#tree [data-file='agent/calc.py']").wait_for()
    assert (server.repo / "agent" / "calc.py").exists() and not (server.repo / "agent" / "core.py").exists()
    page.locator(".tab.on", has_text="calc.py").wait_for()  # the open tab follows the file


def test_delete_asks_then_undo_restores(page, server, session):
    open_app(page)
    page.locator("#tree [data-file='Makefile']").click(button="right")
    menu(page, "Delete")
    page.locator("#dialogTitle", has_text="Delete Makefile?").wait_for()
    page.click("#dialogCancel")
    assert (server.repo / "Makefile").exists()

    page.locator("#tree [data-file='Makefile']").click(button="right")
    menu(page, "Delete")
    confirm(page)
    page.locator("#tree [data-file='Makefile']").wait_for(state="detached")
    assert not (server.repo / "Makefile").exists()
    page.locator(".toast-act", has_text="Undo").click()
    page.locator("#tree [data-file='Makefile']").wait_for()
    assert (server.repo / "Makefile").read_text().startswith("eval-bedrock")


def test_f2_and_delete_keys_in_the_explorer(page, server, session):
    open_app(page)
    page.click("#tree [data-dir='traces']")
    page.click("#tree [data-file='traces/run.jsonl']")
    page.keyboard.press("F2")
    page.locator("#dialog").wait_for()
    page.keyboard.type("spans")
    page.keyboard.press("Enter")
    page.locator("#tree [data-file='traces/spans.jsonl']").wait_for()
    page.click("#tree [data-file='traces/spans.jsonl']")
    page.keyboard.press("Delete")
    confirm(page)
    page.locator("#tree [data-file='traces/spans.jsonl']").wait_for(state="detached")
    assert not (server.repo / "traces" / "spans.jsonl").exists()


def test_delete_key_does_nothing_outside_the_explorer(page, server, session):
    open_app(page)
    page.click("#tree [data-file='Makefile']")
    page.click("#input")
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    assert page.locator("#dialog").is_hidden() and (server.repo / "Makefile").exists()


def test_saving_over_a_change_made_on_disk_asks_first(page, server, session):
    core = server.repo / "agent" / "core.py"
    page.expected_errors.append("409 (Conflict)")
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.locator("#tree [data-file='agent/core.py']").click(button="right")
    menu(page, "Edit")
    page.locator("#codeEdit").wait_for()
    page.keyboard.type("# mine\n")
    core.write_text("# changed elsewhere\n")
    page.click("#fSave")
    page.locator("#dialogTitle", has_text="changed on disk").wait_for()
    page.click("#dialogCancel")
    assert core.read_text() == "# changed elsewhere\n"
    page.click("#fSave")
    page.click("#dialogOk")  # Overwrite
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    assert core.read_text().startswith("# mine\n")


def test_closing_a_tab_with_unsaved_edits_asks(page, server, session):
    open_app(page)
    page.click("#tree [data-file='Makefile']")
    page.click("#fEdit")
    page.locator("#codeEdit").type("more\n")
    page.locator(".tab.on [data-close]").click()
    page.locator("#dialogTitle", has_text="Discard changes").wait_for()
    page.click("#dialogCancel")
    assert page.locator(".tab.dirty").count() == 1
    page.locator(".tab.on [data-close]").click()
    confirm(page)
    page.locator(".tab").wait_for(state="detached")
    assert "more" not in (server.repo / "Makefile").read_text()


def test_empty_explorer_space_offers_new_items(page, server, session):
    open_app(page)
    box = page.locator("#tree").bounding_box()
    page.mouse.click(box["x"] + 40, box["y"] + box["height"] - 20, button="right")
    menu(page, "New Folder…")
    answer(page, "notes")
    page.locator("#tree [data-dir='notes']").wait_for()


# -- following the disk: changes from the agent, the terminal or other apps show up by themselves -----------


def test_explorer_shows_files_and_folders_made_outside_the_page(page, server, session):
    open_app(page)
    page.click("#tree [data-dir='agent']")  # expanded
    page.locator("#tree [data-file='agent/core.py']").wait_for()
    (server.repo / "generated").mkdir()  # like the agent or the terminal
    (server.repo / "agent" / "helpers.py").write_text("x = 1\n")
    page.locator("#tree [data-dir='generated']").wait_for(timeout=5000)
    page.locator("#tree [data-file='agent/helpers.py']").wait_for(timeout=5000)
    (server.repo / "agent" / "helpers.py").unlink()
    page.locator("#tree [data-file='agent/helpers.py']").wait_for(state="detached", timeout=5000)


def test_an_open_file_reloads_when_it_changes_on_disk(page, server, session):
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.locator("#editor code", has_text="a - b").wait_for()
    (server.repo / "agent" / "core.py").write_text("def add(a, b):\n    return a + b  # fixed elsewhere\n")
    page.locator("#editor code", has_text="fixed elsewhere").wait_for(timeout=5000)


def test_unsaved_edits_are_never_replaced_by_a_change_on_disk(page, server, session):
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.locator("#editor code", has_text="a - b").wait_for()
    page.click("#fEdit")
    page.locator("#codeEdit").wait_for()
    page.locator("#codeEdit").press("End")
    page.locator("#codeEdit").type("\n# mine")
    (server.repo / "agent" / "core.py").write_text("theirs = 1\n")
    page.get_by_text("changed on disk. Your unsaved edits are kept").wait_for(timeout=5000)
    assert "# mine" in page.input_value("#codeEdit")


# The line at the top of a scroller, from its scroll position: the view and the editor both draw 20px lines.
TOP_LINE = "(sel) => Math.floor(document.querySelector(sel).scrollTop / 20) + 1"
CARET_LINE = "() => { const t = document.querySelector('#codeEdit'); return t.value.slice(0, t.selectionStart).split('\\n').length; }"


def scroll_to_line(page, sel, n):
    page.evaluate("([sel, n]) => { const el = document.querySelector(sel); el.scrollTop = (n - 1) * 20; "
                  "el.dispatchEvent(new Event('scroll')); }", [sel, n])


def open_long_file(page, server, name="long.py"):
    (server.repo / name).write_text("".join(f"value_{i} = {i}\n" for i in range(1, 301)))
    open_app(page)
    page.click(f"#tree [data-file='{name}']")
    page.locator("#editor code", has_text="value_300").wait_for()


def test_edit_and_done_keep_your_place_in_a_file(page, server, session):
    open_long_file(page, server)
    page.click("#fEdit")  # from the top: the editor opens at line 1, caret there too
    page.locator("#codeEdit").wait_for()
    assert page.evaluate(TOP_LINE, "#codeEdit") == 1 and page.evaluate(CARET_LINE) == 1
    page.click("#fDone")

    scroll_to_line(page, "#edScroll", 120)
    page.click("#fEdit")  # from line 120: the editor shows line 120, with the caret on it
    page.locator("#codeEdit").wait_for()
    assert abs(page.evaluate(TOP_LINE, "#codeEdit") - 120) <= 1
    assert page.evaluate(CARET_LINE) == 120

    scroll_to_line(page, "#codeEdit", 200)
    page.click("#fDone")  # Done: the view shows what the editor had at its top
    page.locator("#edScroll").wait_for()
    assert abs(page.evaluate(TOP_LINE, "#edScroll") - 200) <= 1


def test_a_file_tab_keeps_its_place_when_you_come_back_to_it(page, server, session):
    open_long_file(page, server)
    scroll_to_line(page, "#edScroll", 150)
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.locator("#editor code", has_text="a - b").wait_for()
    page.locator("#editorTabs [data-tab='file:long.py']").click()
    page.locator("#editor code", has_text="value_300").wait_for()
    assert abs(page.evaluate(TOP_LINE, "#edScroll") - 150) <= 1  # the view

    page.click("#fEdit")
    scroll_to_line(page, "#codeEdit", 80)
    page.locator("#editorTabs [data-tab='file:agent/core.py']").click()
    page.locator("#editor code", has_text="a - b").wait_for()
    page.locator("#editorTabs [data-tab='file:long.py']").click()
    page.locator("#codeEdit").wait_for()
    assert abs(page.evaluate(TOP_LINE, "#codeEdit") - 80) <= 1  # and the editor


# Whether the active tab is wholly inside the tab strip's box (not scrolled past either edge).
ACTIVE_TAB_SHOWN = """() => {
  const strip = document.querySelector('#editorTabs').getBoundingClientRect();
  const r = document.querySelector('#editorTabs .tab.on').getBoundingClientRect();
  return r.left >= strip.left - 0.5 && r.right <= strip.right + 0.5;
}"""


def test_the_active_tab_is_always_in_view(page, server, session):
    page.set_viewport_size({"width": 1024, "height": 700})
    for i in range(12):
        (server.repo / f"module_{i:02d}.py").write_text(f"x = {i}\n")
    open_app(page)
    for i in range(12):
        page.click(f"#tree [data-file='module_{i:02d}.py']")
        page.locator("#editorTabs .tab.on", has_text=f"module_{i:02d}.py").wait_for()
        assert page.evaluate(ACTIVE_TAB_SHOWN), f"module_{i:02d}.py's tab is out of sight"
    page.locator("#editorTabs [data-tab='file:module_00.py']").click()  # back to the first: the strip follows
    page.locator("#editorTabs .tab.on", has_text="module_00.py").wait_for()
    assert page.evaluate(ACTIVE_TAB_SHOWN)

    page.fill("#input", "fix two things")
    page.press("#input", "Enter")
    page.locator("#rbReview").click()  # the Review tab opens at the far end of the strip
    page.locator("#editorTabs .tab.on", has_text="Review changes").wait_for()
    assert page.evaluate(ACTIVE_TAB_SHOWN), "the Review tab opened out of sight"


def test_the_mouse_wheel_scrolls_the_tab_strip_sideways(page, server, session):
    page.set_viewport_size({"width": 1024, "height": 700})
    for i in range(12):
        (server.repo / f"module_{i:02d}.py").write_text(f"x = {i}\n")
    open_app(page)
    for i in range(12):
        page.click(f"#tree [data-file='module_{i:02d}.py']")
    page.locator("#editorTabs .tab.on", has_text="module_11.py").wait_for()
    page.evaluate("document.querySelector('#editorTabs').scrollLeft = 0")
    page.locator("#editorTabs").hover()
    page.mouse.wheel(0, 300)
    page.wait_for_function("() => document.querySelector('#editorTabs').scrollLeft > 0", timeout=2_000)


def test_a_binary_file_opens_as_a_binary_file_not_as_text(page, server, session):
    (server.repo / "data.bin").write_bytes(bytes(range(256)) * 4)
    open_app(page)
    page.click("#tree [data-file='data.bin']")
    page.locator("#editor", has_text="Binary file").wait_for()
    assert "1 KB" in page.locator("#editor").text_content() or "1,024" in page.locator("#editor").text_content()
    assert page.locator("#fEdit, #fAsk, #codeEdit, #editor .code-view").count() == 0  # nothing to edit or read as text


def test_a_file_that_isnt_utf8_is_shown_but_not_offered_for_editing(page, server, session):
    (server.repo / "latin1.txt").write_bytes("café crème\n".encode("latin-1"))
    open_app(page)
    page.click("#tree [data-file='latin1.txt']")
    page.locator("#editor code", has_text="cr").wait_for()
    assert page.locator("#fEdit").count() == 0
    assert "UTF-8" in page.locator("#editor .enc-note").text_content()  # says why it can't be edited here
