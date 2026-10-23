"""The Terminal feature as a user drives it: menus, the dropdown, several shells, reloads, exits."""

import re

from uihelpers import open_app

PANE = ".term-pane:not([hidden])"


def menu(page, label):
    page.locator("#ctxMenu .mi span", has_text=re.compile(f"^{re.escape(label)}$")).click()


def run(page, command):
    page.locator(f"{PANE} .xterm-screen").click()
    page.keyboard.type(command)
    page.keyboard.press("Enter")


def wait_output(page, needle, timeout=10_000):
    page.wait_for_function(
        "(n) => (document.querySelector('.term-pane:not([hidden]) .xterm-rows')?.textContent || '').includes(n)",
        arg=needle, timeout=timeout)


def visible_text(page):
    return page.locator(f"{PANE} .xterm-rows").text_content()


def options(page):
    return page.locator("#termSelect option").all_text_contents()


def server_terminals(server):
    return server.app.state.terminals.list()


def test_open_from_title_bar_menu_and_run_a_command(page, server, session):
    open_app(page)
    page.click("#terminalMenuBtn")
    menu(page, "New Terminal")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    assert options(page) == ["1: sh"]
    assert page.locator("#termCwd").text_content().endswith("target")  # the session's folder
    run(page, "echo cp-$((6*7))")
    wait_output(page, "cp-42")


def test_opening_the_panel_tab_starts_a_terminal_only_when_none_exist(page, server, session):
    open_app(page)
    page.click("#terminalTabBtn")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    page.click("[data-ptab=activity]")
    page.click("#terminalTabBtn")
    page.wait_for_timeout(300)
    assert options(page) == ["1: sh"] and len(server_terminals(server)) == 1


def test_several_terminals_switch_from_the_dropdown(page, server, session):
    open_app(page)
    page.click("#terminalTabBtn")
    run(page, "echo first-$((1+1))")
    wait_output(page, "first-2")
    page.click("#termNew")
    page.wait_for_function("() => document.querySelectorAll('#termSelect option').length === 2")
    run(page, "echo second-$((2+2))")
    wait_output(page, "second-4")
    assert "first-2" not in visible_text(page)  # each terminal has its own screen
    assert page.locator("#termCount").text_content() == "2"

    ids = [t.id for t in server_terminals(server)]
    page.select_option("#termSelect", ids[0])
    wait_output(page, "first-2")
    assert "second-4" not in visible_text(page)

    page.click("#terminalMenuBtn")  # the title-bar menu lists both, the active one checked
    items = page.locator("#ctxMenu .mi span").all_text_contents()
    assert any(i.startswith("1: sh") for i in items) and any(i.startswith("2: sh") for i in items)
    menu(page, next(i for i in items if i.startswith("2: sh")))
    wait_output(page, "second-4")


def test_terminals_survive_a_page_reload(page, server, session):
    open_app(page)
    page.click("#terminalTabBtn")
    run(page, "export CP_KEEP=still-here; echo before-$((3*3))")
    wait_output(page, "before-9")
    page.click("#termNew")
    page.wait_for_function("() => document.querySelectorAll('#termSelect option').length === 2")

    page.reload()
    page.locator(f"{PANE} .xterm-screen").wait_for()  # the Terminal tab reopens by itself
    assert len(options(page)) == 2
    page.select_option("#termSelect", server_terminals(server)[0].id)
    wait_output(page, "before-9")  # scrollback replayed
    run(page, "echo $CP_KEEP")
    wait_output(page, "still-here")  # same shell, same state


def test_rename_and_kill(page, server, session):
    open_app(page)
    page.click("#terminalTabBtn")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    page.click("#termRename")
    page.fill("#dialogInput", "dev server")
    page.press("#dialogInput", "Enter")
    page.wait_for_function("() => document.querySelector('#termSelect option')?.textContent === '1: dev server'")
    page.reload()
    page.wait_for_function("() => document.querySelector('#termSelect option')?.textContent === '1: dev server'")

    proc = server_terminals(server)[0].pty.proc
    page.click("#termKill")
    page.locator("#termEmpty").wait_for()
    assert options(page) == [] and server_terminals(server) == []
    proc.wait(timeout=5)
    assert page.locator("#termKill").is_disabled()
    page.click("#termEmptyNew")
    page.wait_for_function("() => document.querySelectorAll('#termSelect option').length === 1")


def test_clean_exit_closes_the_terminal_and_a_failure_stays_open(page, server, session):
    open_app(page)
    page.click("#terminalTabBtn")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    run(page, "exit 0")
    page.locator("#termEmpty").wait_for()  # like VS Code: a clean exit closes it
    assert server_terminals(server) == []

    page.click("#termEmptyNew")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    run(page, "exit 3")
    page.wait_for_function("() => document.querySelector('#termStatus').textContent === 'Exited with code 3'")
    assert "(exited)" in options(page)[0]
    page.click("#termRestart")  # the exited terminal goes away, then a new one appears
    page.wait_for_function("() => { const o = document.querySelectorAll('#termSelect option'); "
                           "return o.length === 1 && !o[0].textContent.includes('exited'); }")
    run(page, "echo back-$((5+5))")
    wait_output(page, "back-10")


def test_open_in_terminal_from_the_explorer(page, server, session):
    open_app(page)
    page.locator("#tree [data-dir='agent']").click(button="right")
    menu(page, "Open in Terminal")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    assert page.locator("#termCwd").text_content().endswith("target/agent")
    run(page, "echo dir-$(basename $(pwd))")
    wait_output(page, "dir-agent")


def test_new_terminal_in_home_folder(page, server, session):
    open_app(page)
    page.click("#terminalMenuBtn")
    menu(page, "New Terminal in Home Folder")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    assert page.locator("#termCwd").text_content() == "~"


def test_selection_goes_to_chat(page, server, session):
    open_app(page)
    page.click("#terminalTabBtn")
    run(page, "echo picked-$((7*6))")
    wait_output(page, "picked-42")
    row = page.locator(f"{PANE} .xterm-rows > div", has_text=re.compile(r"^picked-42")).first
    row.click(click_count=3)  # triple-click selects the line
    page.click("#termSendSel")
    assert "picked-42" in page.input_value("#input")
    assert page.input_value("#input").startswith("Terminal output:")


def test_theme_change_restyles_open_terminals(page, server, session):
    open_app(page)
    page.click("#terminalTabBtn")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    before = page.eval_on_selector(f"{PANE} .xterm-viewport", "el => getComputedStyle(el).backgroundColor")
    page.click("#themeBtn")
    page.wait_for_function("(b) => getComputedStyle(document.querySelector('.term-pane:not([hidden]) "
                           ".xterm-viewport')).backgroundColor !== b", arg=before)


def test_any_key_closes_an_exited_terminal(page, server, session):
    open_app(page)
    page.click("#terminalTabBtn")
    page.locator(f"{PANE} .xterm-screen").wait_for()
    run(page, "exit 2")
    wait_output(page, "Press any key to close")
    page.locator(f"{PANE} .xterm-screen").click()
    page.keyboard.press("x")
    page.locator("#termEmpty").wait_for()
    assert server_terminals(server) == []
