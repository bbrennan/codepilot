"""Steering docs in the UI: the view, creating and editing docs, #name in chat, and what the model receives."""

import re

from uihelpers import open_app


def menu(page, label):
    page.locator("#ctxMenu .mi span", has_text=re.compile(f"^{re.escape(label)}$")).click()


def answer(page, text):
    page.locator("#dialog").wait_for()
    page.fill("#dialogInput", text)
    page.press("#dialogInput", "Enter")


def mod(page):
    return "Meta" if page.evaluate("navigator.platform").startswith("Mac") else "Control"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def steering_rows(page):
    return page.locator("#steeringView .row.steer .name").all_text_contents()


def test_view_lists_docs_from_every_source(page, server, session):
    write(server.repo / ".codepilot/steering/style.md", "Use 4 spaces.")
    api = '---\ninclusion: fileMatch\nfileMatchPattern: "agent/**"\n---\nAPI'
    write(server.repo / ".codepilot/steering/api.md", api)
    write(server.cfg.home / "steering/security.md", "Never log secrets.")
    write(server.repo / "CLAUDE.md", "Claude rules")
    open_app(page)
    page.click("[data-view=steering]")
    page.locator("#steeringView .row.steer").first.wait_for()
    assert set(steering_rows(page)) >= {"style", "api", "security", "CLAUDE"}
    assert page.locator("#steeringView .row.steer:has-text('api') .incl").text_content() == "agent/**"

    page.locator("#steeringView .row.steer", has_text="CLAUDE").click()  # a workspace file: opens like any other
    page.locator(".code-view", has_text="Claude rules").wait_for()  # Markdown opens as raw text


def test_create_a_workspace_doc_edit_save_and_the_model_follows_it(page, server, session):
    open_app(page)
    page.click("[data-view=steering]")
    page.click("#steerNew")
    menu(page, "This workspace: always on")
    answer(page, "coding-standards")
    page.locator("#codeEdit").wait_for()  # opens in the editor with a template
    doc = server.repo / ".codepilot/steering/coding-standards.md"
    assert "inclusion: always" in doc.read_text()
    page.fill("#codeEdit", "---\ninclusion: always\n---\nAlways answer in British English.")
    page.keyboard.press(f"{mod(page)}+s")
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    page.locator("#steeringView .row.steer", has_text="coding-standards").wait_for()

    page.fill("#input", "hello")
    page.press("#input", "Enter")
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    system = "\n".join(b["text"] for b in server.llm.calls[-1]["system"])
    assert "Always answer in British English." in system


def test_file_match_doc_from_the_menu(page, server, session):
    open_app(page)
    page.click("[data-view=steering]")
    page.click("#steerNew")
    menu(page, "This workspace: for matching files…")
    answer(page, "agent-rules")
    page.locator("#dialogTitle", has_text="Which files?").wait_for()
    page.fill("#dialogInput", "agent/**/*.py")
    page.press("#dialogInput", "Enter")
    page.locator("#codeEdit").wait_for()
    assert 'fileMatchPattern: "agent/**/*.py"' in (server.repo / ".codepilot/steering/agent-rules.md").read_text()


def test_global_doc_create_and_edit(page, server, session):
    open_app(page)
    page.click("[data-view=steering]")
    page.click("#steerNew")
    menu(page, "All workspaces: always on")
    answer(page, "security")
    page.locator("#codeEdit").wait_for()
    page.fill("#codeEdit", "Never print tokens.")
    page.click("#fSave")
    page.wait_for_function("() => !document.querySelector('.tab.on').classList.contains('dirty')")
    assert (server.cfg.home / "steering/security.md").read_text() == "Never print tokens."
    assert page.locator(".tab.on .label").text_content() == "security.md"


def test_hash_menu_attaches_a_manual_doc_and_shows_a_chip(page, server, session):
    write(server.repo / ".codepilot/steering/release.md", "---\ninclusion: manual\n---\nBump the version first.")
    open_app(page)
    page.click("#input")
    page.keyboard.type("do the release per #rel")
    page.locator("#mentionPop .opt", has_text="#release").wait_for()
    page.keyboard.press("Enter")
    assert page.input_value("#input") == "do the release per #release "
    page.keyboard.press("Enter")
    page.locator(".steer-chip", has_text="steering: release").wait_for()
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    sent = str(server.llm.calls[-1]["messages"][-1])
    assert "Bump the version first." in sent
    page.reload()  # the chip survives a reload; the doc's text isn't shown as a user message
    page.locator(".steer-chip", has_text="steering: release").wait_for()
    assert "Bump the version" not in page.locator("#transcript").text_content()


def test_generate_foundation_docs_asks_codepilot(page, server, session):
    open_app(page)
    page.click("[data-view=steering]")
    page.click("#steerFoundation")
    page.locator(".msg.user", has_text=".codepilot/steering/product.md").wait_for()
