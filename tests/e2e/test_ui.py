"""The rest of the IDE, end to end: folders, explorer, chat, proposals, models, modes, memory, sessions."""

import re

from uihelpers import open_app


def menu(page, label):
    page.locator("#ctxMenu .mi span", has_text=re.compile(f"^{re.escape(label)}$")).click()


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def wait_idle(page):
    page.wait_for_function("() => !document.querySelector('#stopBtn') || document.querySelector('#stopBtn').hidden")
    page.locator("#sendBtn").wait_for()


def clipboard(page):
    return page.evaluate("() => navigator.clipboard.readText()")


# -- folders and the explorer ---------------------------------------------------------------------


def test_open_folder_by_browsing(page, server):
    open_app(page, wait_tree=False)
    page.click("#workspaceBtn")
    page.locator("#folderDialog").wait_for()
    page.fill("#fdInput", str(server.repo.parent))
    page.press("#fdInput", "Enter")
    page.locator("#fdList [data-fdpath$='/target']").click()
    assert page.locator("#fdOpen").text_content() == "Open selected"
    page.click("#fdOpen")
    page.wait_for_function("() => document.querySelector('#workspaceName').textContent === 'target'")
    page.locator("#tree [data-dir='agent']").wait_for()
    assert server.store.list_sessions()[0].repo.endswith("target")


def test_folder_dialog_navigates_with_double_click_and_up(page, server):
    open_app(page, wait_tree=False)
    page.click("#workspaceBtn")
    page.fill("#fdInput", str(server.repo))
    page.press("#fdInput", "Enter")
    page.locator("#fdList [data-fdpath$='/agent']").dblclick()
    page.wait_for_function("() => document.querySelector('#fdInput').value.endsWith('/target/agent')")
    page.click("#fdUp")
    page.wait_for_function("() => document.querySelector('#fdInput').value.endsWith('/target')")
    page.keyboard.press("Escape")
    assert page.locator("#folderDialog").is_hidden()


def _slow_first_listing(page, delay_ms=800):
    """Hold back the dialog's first (home folder) listing, like a slow network drive or iCloud folder."""
    state = {"held": False}

    def handle(route):
        if not state["held"] and "path=&" in route.request.url:
            state["held"] = True
            page.wait_for_timeout(delay_ms)
        route.continue_()

    page.route("**/api/browse*", handle)


def test_typing_a_path_before_the_first_listing_arrives(page, server):
    open_app(page, wait_tree=False)
    _slow_first_listing(page)
    page.click("#workspaceBtn")
    page.fill("#fdInput", str(server.repo))  # pasted before the home listing came back
    page.wait_for_timeout(1000)
    assert page.input_value("#fdInput") == str(server.repo)  # not overwritten by the late listing
    page.press("#fdInput", "Enter")
    page.locator("#fdList [data-fdpath$='/agent']").wait_for()


def test_a_slow_earlier_listing_never_replaces_a_newer_one(page, server):
    open_app(page, wait_tree=False)
    _slow_first_listing(page)
    page.click("#workspaceBtn")
    page.fill("#fdInput", str(server.repo))
    page.press("#fdInput", "Enter")
    page.locator("#fdList [data-fdpath$='/agent']").wait_for()
    page.wait_for_timeout(1000)  # the held-back home listing arrives now
    assert page.locator("#fdList [data-fdpath$='/agent']").count() == 1
    assert page.input_value("#fdInput") == str(server.repo)


def test_explorer_expands_opens_files_and_copies_paths(page, server, session):
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.locator("#tree [data-file='agent/core.py']").click()
    page.locator("#editor").get_by_text("return a - b").wait_for()

    page.locator("#tree [data-file='agent/core.py']").click(button="right")
    menu(page, "Copy relative path")
    assert clipboard(page) == "agent/core.py"
    page.locator("#tree [data-file='agent/core.py']").click(button="right")
    menu(page, "Copy absolute path")
    assert clipboard(page) == f"{server.repo}/agent/core.py"
    page.locator("#tree [data-file='agent/core.py']").click(button="right")
    menu(page, "Copy @reference")
    assert clipboard(page) == "@agent/core.py"

    page.locator("#tree [data-file='agent/core.py']").click()  # select, then the keyboard shortcut copies it
    page.keyboard.press("Meta+c" if page.evaluate("navigator.platform").startswith("Mac") else "Control+c")
    assert clipboard(page) == "agent/core.py"


def test_reference_button_and_at_mentions(page, server, session):
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.locator("#tree [data-file='agent/core.py']").hover()
    page.locator("#tree [data-file='agent/core.py'] [data-at]").click()
    assert page.input_value("#input").strip() == "@agent/core.py"
    page.fill("#input", "")
    page.type("#input", "look at @tes")
    page.locator("#mentionPop .opt").first.wait_for()
    page.keyboard.press("Enter")
    assert page.input_value("#input") == "look at @tests/test_core.py "


# -- chat, proposals and memory -------------------------------------------------------------------


def test_chat_streams_markdown_and_updates_context_meter(page, server, session):
    open_app(page)
    send(page, "hello there")
    page.locator(".msg.assistant strong", has_text="Hello").wait_for()
    wait_idle(page)
    assert page.locator(".msg.assistant pre code").count() >= 1
    assert re.match(r"context \d+% · ", page.locator("#ctxText").text_content())
    assert page.locator("#sbTokens").text_content() != "0 tokens"
    assert page.locator("#chatTitle").text_content() == "hello there"
    page.reload()  # the transcript is stored, not just painted
    page.locator(".msg.user", has_text="hello there").wait_for()
    page.locator(".msg.assistant strong", has_text="Hello").wait_for()


def test_proposal_apply_and_undo_change_the_file(page, server, session):
    core = server.repo / "agent" / "core.py"
    open_app(page)
    send(page, "fix the add bug")
    card = page.locator(".card[data-prop]")
    card.wait_for()
    assert "a + b" in card.text_content()
    assert page.locator("#changesBadge").text_content() == "1"
    wait_idle(page)
    assert "a - b" in core.read_text()  # nothing is written before approval

    card.locator("[data-apply]").click()
    page.wait_for_function("() => document.querySelector('.card[data-prop] .status').textContent === 'applied'")
    assert "a + b" in core.read_text()
    assert page.locator("#changesBadge").is_hidden()

    card.locator("[data-revert]").click()
    page.wait_for_function("() => document.querySelector('.card[data-prop] .status').textContent === 'reverted'")
    assert "a - b" in core.read_text()


def test_reject_leaves_the_file_alone(page, server, session):
    core = server.repo / "agent" / "core.py"
    open_app(page)
    send(page, "fix it please")
    page.locator(".card[data-prop] [data-reject]").click()
    page.wait_for_function("() => document.querySelector('.card[data-prop] .status').textContent === 'rejected'")
    assert "a - b" in core.read_text()


def test_stop_button_cancels_a_long_reply(page, server, session):
    open_app(page)
    send(page, "be slow")
    page.locator("#stopBtn").wait_for()
    page.click("#stopBtn")
    wait_idle(page)
    assert page.locator("#sendBtn").is_visible()


def test_slash_menu_and_compact(page, server, session):
    open_app(page)
    send(page, "hello")
    wait_idle(page)
    page.fill("#input", "")
    page.type("#input", "/comp")
    page.locator("#mentionPop .opt", has_text="/compact").wait_for()
    page.keyboard.press("Enter")
    assert page.input_value("#input") == "/compact "
    page.type("#input", "the add bug")
    page.keyboard.press("Enter")
    wait_idle(page)
    page.click("[data-view=memory]")
    page.locator("#memoryView", has_text="SUMMARY: we fixed the add bug").wait_for()
    assert "summarised" in page.locator("#ctxText").text_content()


def test_workspace_notes_save(page, server, session):
    open_app(page)
    page.click("[data-view=memory]")
    page.fill("#notesBox", "- tests need make db-up first")
    page.click("#saveNotes")  # straight away: typing before the saved notes load must not be lost
    page.get_by_text("Notes saved").wait_for()
    assert "make db-up" in server.store.read_notes(str(server.repo))


# -- models, modes, sessions, theme ---------------------------------------------------------------


def test_model_dropdown_lists_account_models_and_remembers_choice(page, server, session):
    open_app(page)
    page.wait_for_function("() => document.querySelectorAll('#tier optgroup').length === 3")
    groups = page.eval_on_selector_all("#tier optgroup", "gs => gs.map(g => g.label)")
    assert groups == ["Tiers", "Models on your account", "Not enabled for this account"]
    fast = page.locator("#tier option[value='tier:fast']").text_content()
    assert "haiku-4-5" in fast and "(fallback)" in fast  # Haiku 5.5 is pending, so the fast tier falls back
    off = page.locator("#tier optgroup[label='Not enabled for this account'] option").first
    assert off.is_disabled() and "pending onboarding" in off.get_attribute("title")

    page.select_option("#tier", "model:anthropic.claude-opus-5-5")
    page.wait_for_timeout(200)
    assert server.store.get_session(session.id).model == "anthropic.claude-opus-5-5"
    page.reload()
    page.wait_for_function("() => document.querySelector('#tier').value === 'model:anthropic.claude-opus-5-5'")
    send(page, "hi")
    wait_idle(page)
    assert server.llm.calls[-1]["model"] == "anthropic.claude-opus-5-5"


def test_mode_switch_changes_composer_and_persists(page, server, session):
    open_app(page)
    page.wait_for_function("() => document.querySelectorAll('#modeSelect option').length > 2")
    modes = page.eval_on_selector_all("#modeSelect option", "os => os.map(o => o.value)")
    target = "plan" if "plan" in modes else modes[1]
    page.select_option("#modeSelect", target)
    page.wait_for_timeout(200)
    assert server.store.get_session(session.id).mode == target
    placeholder = page.get_attribute("#input", "placeholder")
    page.reload()
    page.wait_for_function("(m) => document.querySelector('#modeSelect').value === m", arg=target)
    assert page.get_attribute("#input", "placeholder") == placeholder


def test_switching_sessions_replays_each_transcript(page, server, session):
    other = server.store.create_session(str(server.repo), "main")
    open_app(page)
    page.click("[data-view=sessions]")
    page.locator(f".session[data-id='{session.id}']").click()
    send(page, "message for the first session")
    wait_idle(page)
    page.locator(f".session[data-id='{other.id}']").click()
    page.wait_for_function("() => !document.querySelector('#transcript').textContent.includes('first session')")
    send(page, "message for the second session")
    wait_idle(page)
    page.locator(f".session[data-id='{session.id}']").click()
    page.locator(".msg.user", has_text="message for the first session").wait_for()
    assert "second session" not in page.locator("#transcript").text_content()


def test_new_session_keeps_the_folder(page, server, session):
    open_app(page)
    page.click("#newChatBtn")
    page.wait_for_function("(n) => document.querySelectorAll('.session').length === n", arg=2)
    assert page.locator("#workspaceName").text_content() == "target"
    assert all(s.repo == str(server.repo) for s in server.store.list_sessions())


def test_theme_and_layout_persist(page, server, session):
    open_app(page)
    before = page.evaluate("document.documentElement.dataset.theme || ''")
    page.click("#themeBtn")
    after = page.evaluate("document.documentElement.dataset.theme")
    assert after and after != before
    page.click("#toggleSidebar")
    page.click("#togglePanel")
    page.reload()
    page.wait_for_function("(t) => document.documentElement.dataset.theme === t", arg=after)
    assert page.evaluate("document.querySelector('#ide').classList.contains('no-sidebar')")
    assert page.evaluate("document.querySelector('#ide').classList.contains('no-panel')")
    page.click("[data-view=search]")  # choosing a view reveals the sidebar again, and that sticks too
    page.reload()
    page.wait_for_function("() => !document.querySelector('#ide').classList.contains('no-sidebar')")


def test_run_command_from_the_output_panel(page, server, session):
    open_app(page)
    page.click("[data-ptab=output]")
    page.fill("#cmdInput", "echo panel-$((2+3))")
    page.press("#cmdInput", "Enter")
    page.locator("#output pre", has_text="panel-5").wait_for()
    assert page.locator("#output .status").text_content() == "exit 0"
