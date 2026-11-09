"""Getting to your sessions: the chat's title opens a searchable list of them, and the Sessions sidebar is searchable,
grouped by folder, and what a first visit shows (spec session-switcher). Before this, past sessions were behind the
clock icon, or on the welcome page you only saw after pressing +."""

import json

from uihelpers import open_app


def sessions(server, tmp_path):
    """Three sessions, oldest first: two in the sample repo, one in another folder. The `session` fixture's is newest."""
    other = tmp_path / "parser-lib"
    other.mkdir()
    (other / "parse.py").write_text("def parse(): ...\n")
    store = server.store
    docs = store.create_session(str(server.repo), "main")
    store.update_session(docs.id, title="write the docs")
    parser = store.create_session(str(other), "main")
    store.update_session(parser.id, title="fix the tokenizer")
    loose = store.create_session("", "main")
    store.update_session(loose.id, title="a question")
    return docs, parser, loose


def shown(page, rows):
    return page.evaluate("(sel) => [...document.querySelectorAll(sel)].filter((r) => !r.hidden)"
                         ".map((r) => r.querySelector('.t').textContent)", rows)


def test_the_chat_title_switches_sessions(page, server, session, tmp_path):
    docs, parser, loose = sessions(server, tmp_path)
    server.store.update_session(session.id, title="the newest")
    open_app(page)
    assert page.locator("#chatTitle").text_content() == "the newest"
    page.click("#chatTitleBtn")
    pop = page.locator("#sessPop")
    pop.wait_for()
    assert pop.locator(".opt").first.text_content().strip() == "New session"  # starting afresh comes first
    assert shown(page, "#sessPop .sess-opt") == ["the newest", "a question", "fix the tokenizer", "write the docs"]
    assert pop.locator(".sess-opt.on .t").text_content() == "the newest"  # the one open
    assert "parser-lib" in pop.locator(f".sess-opt[data-id='{parser.id}']").text_content()  # its folder

    page.fill("#sessSearch", "TOKEN")  # by title, any case
    assert shown(page, "#sessPop .sess-opt") == ["fix the tokenizer"]
    page.press("#sessSearch", "Enter")
    page.wait_for_function("() => document.querySelector('#chatTitle').textContent === 'fix the tokenizer'")
    assert pop.is_hidden()
    assert page.locator("#workspaceName").text_content() == "parser-lib"

    page.click("#chatTitleBtn")
    assert page.locator("#sessSearch").input_value() == ""  # a fresh search each time
    page.fill("#sessSearch", "target")  # by folder: the sample repo's sessions
    assert shown(page, "#sessPop .sess-opt") == ["the newest", "write the docs"]
    page.press("#sessSearch", "ArrowDown")
    page.press("#sessSearch", "Enter")
    page.wait_for_function("() => document.querySelector('#chatTitle').textContent === 'write the docs'")

    page.click("#chatTitleBtn")
    page.press("#sessSearch", "Escape")
    assert pop.is_hidden()
    page.click("#chatTitleBtn")
    page.click("#transcript")  # a click outside closes it too
    assert pop.is_hidden()
    assert page.locator("#chatTitle").text_content() == "write the docs"

    page.click("#chatTitleBtn")
    pop.locator(f".sess-opt[data-id='{loose.id}']").click()
    page.wait_for_function("() => document.querySelector('#chatTitle').textContent === 'a question'")
    page.click("#chatTitleBtn")
    pop.locator(".sess-new").click()
    page.wait_for_function("(n) => document.querySelectorAll('#sessionList .session').length === n", arg=5)
    assert page.locator("#chatTitle").text_content() == "New session"


def test_a_working_session_spins_in_the_switcher(page, server, session, tmp_path):
    docs, *_ = sessions(server, tmp_path)

    def busy(route):
        listed = json.loads(route.fetch().text())
        route.fulfill(json=[{**s, "busy": s["id"] == docs.id} for s in listed])

    page.route("**/api/sessions", busy)
    open_app(page, wait_tree=False)  # (the newest session has no folder)
    page.click("#chatTitleBtn")
    assert page.locator(f"#sessPop .sess-opt[data-id='{docs.id}'] .spinner").count() == 1
    assert page.locator("#sessPop .sess-opt .spinner").count() == 1


def test_the_sidebar_groups_sessions_by_folder_and_filters(page, server, session, tmp_path):
    docs, parser, loose = sessions(server, tmp_path)
    server.store.update_session(parser.id, title="fix the tokenizer again")  # now the newest
    open_app(page)
    page.click("[data-view=sessions]")
    groups = page.evaluate("""() => [...document.querySelectorAll('#sessionList .sess-group')].map((g) => ({
      name: g.querySelector('.sess-gh').textContent,
      rows: [...g.querySelectorAll('.session .t')].map((t) => t.textContent) }))""")
    assert groups == [  # the newest session's folder first; newest first in each
        {"name": "parser-lib", "rows": ["fix the tokenizer again"]},
        {"name": "No folder", "rows": ["a question"]},
        {"name": "target", "rows": ["write the docs", "New session"]},
    ]
    page.fill("#sessFilter", "docs")
    assert shown(page, "#sessionList .session") == ["write the docs"]
    assert page.locator("#sessionList .sess-group:not([hidden])").count() == 1  # empty groups go too
    page.fill("#sessFilter", "parser")
    assert shown(page, "#sessionList .session") == ["fix the tokenizer again"]  # by folder
    page.fill("#sessFilter", "nothing like it")
    page.locator("#sessionList .sess-none").wait_for()
    page.fill("#sessFilter", "")
    assert len(shown(page, "#sessionList .session")) == 4


def test_a_search_survives_the_refresh_while_a_session_works(page, server, session, tmp_path):
    sessions(server, tmp_path)
    open_app(page, wait_tree=False)
    page.click("[data-view=sessions]")
    page.fill("#sessFilter", "docs")
    page.evaluate("loadSessions()")  # what the 4-second poll does while a session works
    page.wait_for_function("() => document.querySelectorAll('#sessionList .session').length === 4")
    assert shown(page, "#sessionList .session") == ["write the docs"]


def test_a_first_visit_shows_the_sessions(page, server, session):
    page.goto("/")  # no view remembered (open_app remembers the Explorer for the other tests)
    page.locator(f"#sessionList .session[data-id='{session.id}']").wait_for()
    assert page.locator(".sidebar .view[data-view=sessions]").is_visible()
    page.click("[data-view=explorer]")
    page.reload()
    page.locator("#tree [data-file]").first.wait_for()  # a view you chose is kept


# -- from review: keyboard, screen readers and refreshes ------------------------------------------------------------


def test_a_refresh_keeps_the_highlighted_session(page, server, session, tmp_path):
    docs, parser, loose = sessions(server, tmp_path)
    server.store.update_session(session.id, title="the newest")
    open_app(page)
    page.click("#chatTitleBtn")
    page.press("#sessSearch", "ArrowDown")  # "a question", the second
    server.store.update_session(parser.id, title="fix the tokenizer")  # it moves to the top
    page.evaluate("loadSessions()")
    page.wait_for_function("() => document.querySelector('#sessPop .sess-opt .t').textContent === 'fix the tokenizer'")
    page.press("#sessSearch", "Enter")
    page.wait_for_function("() => document.querySelector('#chatTitle').textContent === 'a question'")


def test_new_session_can_be_chosen_with_the_keyboard(page, server, session):
    open_app(page)
    page.click("#chatTitleBtn")
    page.press("#sessSearch", "ArrowUp")  # above the first session: New session
    assert page.locator("#sessPop .sess-new").get_attribute("aria-selected") == "true"
    page.press("#sessSearch", "Enter")
    page.wait_for_function("() => document.querySelectorAll('#sessionList .session').length === 2")


def test_screen_readers_hear_which_session_enter_opens(page, server, session, tmp_path):
    sessions(server, tmp_path)
    open_app(page, wait_tree=False)  # (the newest session has no folder)
    page.click("#chatTitleBtn")
    box = page.locator("#sessSearch")
    assert box.get_attribute("role") == "combobox" and box.get_attribute("aria-controls") == "sessPopList"
    assert box.get_attribute("aria-expanded") == "true"
    for _ in range(2):
        active = box.get_attribute("aria-activedescendant")
        option = page.locator(f"#{active}")
        assert option.get_attribute("role") == "option" and option.get_attribute("aria-selected") == "true"
        page.press("#sessSearch", "ArrowDown")
    assert box.get_attribute("aria-activedescendant") != active


def test_enter_that_ends_an_ime_composition_doesnt_pick(page, server, session, tmp_path):
    sessions(server, tmp_path)
    open_app(page, wait_tree=False)  # (the newest session has no folder)
    page.click("#chatTitleBtn")
    page.fill("#sessSearch", "docs")  # mid-composition: "write the docs" would be picked
    page.evaluate("""() => document.querySelector('#sessSearch').dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true, cancelable: true }))""")
    assert page.locator("#sessPop").is_visible()
    assert page.locator("#chatTitle").text_content() == "a question"  # still the one open
