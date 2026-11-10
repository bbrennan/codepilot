"""Several folders in a session (spec multi-folder): the folder button is a menu that adds a folder rather than replacing
the session's; each folder is a top-level entry in the Explorer, the main one first; files in an added folder open,
edit and save; a folder can be removed or made main; a folder that's gone says so."""

import shutil

from test_files_ui import menu, mod
from uihelpers import open_app


def api_folder(tmp_path):
    root = tmp_path / "api"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("PORT = 8000\n")
    return root.resolve()


def roots(page):
    return page.locator("#tree .row.root .name").all_text_contents()


def pick(page, folder):
    """Choose `folder` in the folder dialog."""
    page.locator("#folderDialog").wait_for()
    page.fill("#fdInput", str(folder.parent))
    page.press("#fdInput", "Enter")
    page.locator(f"#fdList [data-fdpath$='/{folder.name}']").click()
    page.click("#fdOpen")


def test_the_folder_button_adds_a_folder_to_the_session(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    open_app(page)
    assert roots(page) == []  # one folder: the Explorer looks as it always did
    page.click("#workspaceBtn")
    items = page.locator("#ctxMenu .mi").all_text_contents()
    assert items[0].startswith("target") and "Add folder…" in items and "Open folder in a new session…" in items
    menu(page, "Add folder…")
    pick(page, api)
    page.wait_for_function("() => document.querySelectorAll('#tree .row.root').length === 2")
    assert roots(page) == ["target", "api"]  # the main folder first
    page.locator(f"#tree [data-dir='{api}/src']").wait_for()
    page.locator("#tree [data-dir='agent']").wait_for()  # the main folder's tree is still there
    sess = server.store.get_session(session.id)
    assert sess.repo == str(server.repo.resolve()) and sess.folders == [str(api)]  # added, not replaced
    assert len(server.store.list_sessions()) == 1

    page.reload()
    page.locator(f"#tree [data-dir='{api}/src']").wait_for()
    assert roots(page) == ["target", "api"]


def test_a_file_in_an_added_folder_opens_and_saves(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.click(f"#tree [data-dir='{api}/src']")
    page.click(f"#tree [data-file='{api}/src/app.py']")
    page.locator("#editor code", has_text="PORT = 8000").wait_for()
    page.click("#fEdit")
    page.locator("#codeEdit").wait_for()
    page.keyboard.type("DEBUG = True\n")  # (at the top)
    page.keyboard.press(f"{mod(page)}+s")
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    assert (api / "src" / "app.py").read_text() == "DEBUG = True\nPORT = 8000\n"


def test_an_added_folder_can_be_made_main_or_removed(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.locator("#tree .row.root", has_text="api").click(button="right")
    menu(page, "Make main folder")
    page.wait_for_function("() => document.querySelector('#workspaceName').textContent.startsWith('api')")
    page.wait_for_function("() => document.querySelector('#tree .row.root .name')?.textContent === 'api'")
    assert roots(page) == ["api", "target"]
    sess = server.store.get_session(session.id)
    assert sess.repo == str(api) and sess.folders == [str(server.repo.resolve())]

    page.locator("#tree .row.root", has_text="target").click(button="right")
    menu(page, "Remove from session")
    page.wait_for_function("() => !document.querySelector('#tree .row.root')")  # one folder again
    page.locator("#tree [data-dir='src']").wait_for()
    assert server.store.get_session(session.id).folders == []
    assert (server.repo / "agent" / "core.py").exists()  # removed from the session, not from the disk


def test_a_folder_that_is_gone_says_so(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    shutil.rmtree(api)
    open_app(page)
    gone = page.locator("#tree .root-missing")
    gone.wait_for()
    assert "can't be found" in gone.text_content()
    gone.locator("button", has_text="Remove from session").click()
    page.wait_for_function("() => !document.querySelector('#tree .row.root')")
    assert server.store.get_session(session.id).folders == []


def test_a_folder_can_open_in_a_new_session(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    open_app(page)
    page.click("#workspaceBtn")
    menu(page, "Open folder in a new session…")
    pick(page, api)
    page.wait_for_function("() => document.querySelector('#workspaceName').textContent === 'api'")
    assert len(server.store.list_sessions()) == 2
    assert server.store.get_session(session.id).repo == str(server.repo.resolve())  # the first session kept its folder


# -- from review ------------------------------------------------------------------------------------------------------


def test_a_folder_change_that_lands_after_switching_sessions_leaves_the_new_one_alone(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    lib = tmp_path / "lib"
    (lib / "pkg").mkdir(parents=True)
    other = server.store.create_session(str(lib), "main")
    server.store.update_session(session.id, folders=[str(api)], title="with api")  # the newest: it opens
    held = []
    page.route(f"**/api/sessions/{session.id}", lambda r: held.append(r) if r.request.method == "PATCH" else r.continue_())
    open_app(page)
    page.locator("#tree .row.root", has_text="api").click(button="right")
    menu(page, "Remove from session")
    page.wait_for_function("() => true")
    page.click("#chatTitleBtn")
    page.locator(f"#sessPop .sess-opt[data-id='{other.id}']").click()
    page.wait_for_function("() => document.querySelector('#workspaceName').textContent === 'lib'")
    page.wait_for_timeout(100)
    assert held
    held[0].continue_()  # the removal answers now
    page.wait_for_timeout(500)
    assert page.locator("#workspaceName").text_content() == "lib"
    page.locator("#tree [data-dir='pkg']").wait_for()


def test_making_a_folder_main_keeps_unsaved_edits(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.click("#fEdit")
    page.locator("#codeEdit").wait_for()
    page.keyboard.type("# draft\n")
    page.wait_for_function("() => document.querySelector('.tab.on').classList.contains('dirty')")
    page.locator("#tree .row.root", has_text="api").click(button="right")
    menu(page, "Make main folder")
    page.locator(".toast", has_text="unsaved").wait_for()
    assert server.store.get_session(session.id).repo == str(server.repo.resolve())  # not changed
    assert page.locator(".tab.dirty").count() == 1


def test_an_added_folders_files_have_their_own_full_paths(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    assert page.evaluate("(p) => absPath(p)", f"{api}/src") == f"{api}/src"  # Copy path, Open in Terminal
    assert page.evaluate("() => absPath('agent')") == f"{server.repo.resolve()}/agent"


def test_new_files_at_the_top_of_an_added_folder_show_up(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.locator(f"#tree [data-dir='{api}/src']").wait_for()
    (api / "NOTES.md").write_text("made in the terminal\n")
    page.locator(f"#tree [data-file='{api}/NOTES.md']").wait_for(timeout=6000)


def test_new_file_goes_in_the_folder_whose_entry_you_clicked(page, server, session, tmp_path):
    from test_files_ui import answer

    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.locator("#tree .row.root", has_text="api").click()
    page.click("#newFileBtn")
    answer(page, "todo.md")
    page.locator("#codeEdit").wait_for()
    assert (api / "todo.md").exists() and not (server.repo / "todo.md").exists()


# -- finding things in every folder (task 2) ------------------------------------------------------------------------


def test_go_to_file_finds_a_file_in_an_added_folder(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.click("#paletteBtn")
    page.fill("#paletteInput", "app.py")
    opt = page.locator("#paletteList .opt", has_text="app.py")
    opt.wait_for()
    assert opt.locator(".dir").text_content() == "api/src"  # which folder it's in, not a long full path
    page.press("#paletteInput", "Enter")
    page.locator("#editor code", has_text="PORT = 8000").wait_for()


def test_the_search_view_finds_text_in_an_added_folder(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.click("[data-view=search]")
    page.fill("#grepInput", "PORT")
    row = page.locator("#grepResults .row", has_text="app.py")
    row.wait_for()
    assert row.locator(".meta").text_content() == "api/src"
    page.locator("#grepResults .grep-hit").first.click()
    page.locator("#editor code", has_text="PORT = 8000").wait_for()


def test_at_mentions_suggest_files_in_an_added_folder(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.type("#input", "look at @app.p")
    opt = page.locator("#mentionPop .opt", has_text="app.py")
    opt.wait_for()
    assert "api/src" in opt.text_content()
    page.keyboard.press("Enter")
    assert page.input_value("#input") == f"look at @{api}/src/app.py "


def test_the_changes_view_lists_an_added_folders_git_changes(page, server, session, tmp_path):
    import subprocess

    api = api_folder(tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "trunk", str(api)], check=True)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    page.click("[data-view=changes]")
    head = page.locator("#gitList .group-head", has_text="api")
    head.wait_for()
    assert "trunk" in head.text_content()
    page.locator(f"#gitList [data-gitfile='{api}/src/']").wait_for()  # untracked: git shows the folder


# -- from the release review ----------------------------------------------------------------------------------------


def test_review_shows_changes_as_they_now_are_after_a_folder_change(page, server, session, tmp_path):
    from codepilot import tools

    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    ctx = tools.ToolContext(root=server.repo.resolve(), cfg=server.cfg, store=server.store, session_id=session.id,
                            folders=[api])
    tools.propose_edit(ctx, "agent/core.py", "a - b", "a + b")
    tools.propose_edit(ctx, str(api / "src" / "app.py"), "PORT = 8000", "PORT = 9000")
    open_app(page)
    page.locator("#transcript .card.prop").nth(1).wait_for()
    page.locator("#tree .row.root", has_text="api").click(button="right")
    menu(page, "Make main folder")
    main = str(server.repo.resolve())
    page.wait_for_function("(p) => state.proposals.get(1)?.path === p + '/agent/core.py'", arg=main)
    assert page.evaluate("() => state.proposals.get(2).path") == "src/app.py"  # now in the main folder
    page.locator("#tree .row.root", has_text="target").click(button="right")
    menu(page, "Remove from session")
    page.wait_for_function("() => state.proposals.get(1)?.status === 'outdated'")  # its folder left the session


def test_dropping_on_a_folders_entry_drops_into_that_folder(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    server.store.update_session(session.id, folders=[str(api)])
    open_app(page)
    at = "(sel) => dropDir({ target: document.querySelector(sel) })"
    assert page.evaluate(at, f"#tree .row.root[data-root='{api}']") == str(api)
    assert page.evaluate(at, "#tree .row.root .name") == ""  # the main folder's entry: its top level


def test_a_reload_after_a_folder_change_that_lands_late_leaves_the_new_session_alone(page, server, session, tmp_path):
    api = api_folder(tmp_path)
    lib = tmp_path / "lib"
    (lib / "pkg").mkdir(parents=True)
    other = server.store.create_session(str(lib), "main")
    server.store.update_session(session.id, folders=[str(api)], title="with api")
    held, patched = [], []

    def route(r):
        if r.request.method == "PATCH":
            patched.append(1)
            r.continue_()
        elif patched and not held:
            held.append(r)  # the session's reload after the folder change: answered late
        else:
            r.continue_()

    page.route(f"**/api/sessions/{session.id}", route)
    open_app(page)
    page.locator("#tree .row.root", has_text="api").click(button="right")
    menu(page, "Remove from session")
    page.wait_for_function("() => true")
    page.wait_for_timeout(300)
    assert held
    page.click("#chatTitleBtn")
    page.locator(f"#sessPop .sess-opt[data-id='{other.id}']").click()
    page.wait_for_function("() => document.querySelector('#workspaceName').textContent === 'lib'")
    held[0].continue_()
    page.wait_for_timeout(500)
    assert page.locator("#workspaceName").text_content() == "lib"
    assert page.evaluate("() => state.sid") == other.id
