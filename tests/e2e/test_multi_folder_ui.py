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
