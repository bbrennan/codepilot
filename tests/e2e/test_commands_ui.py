"""Slash commands: run in the app without a model call (except /compact and skills)."""

from uihelpers import open_app


def run(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def model_calls(server):
    return [c for c in server.llm.calls if "messages" in c]


def test_help_lists_commands_without_calling_the_model(page, server, session):
    open_app(page)
    page.type("#input", "/hel")
    page.locator("#mentionPop .opt", has_text="/help").wait_for()
    page.keyboard.press("Enter")  # picking a no-argument command runs it
    card = page.locator(".card.cmd-help")
    card.wait_for()
    assert "/model" in card.text_content() and "/spec" in card.text_content()
    assert page.input_value("#input") == "" and model_calls(server) == []


def test_mode_commands_switch_and_send_the_rest(page, server, session):
    open_app(page)
    page.wait_for_function("() => document.querySelectorAll('#modeSelect option').length > 2")
    run(page, "/plan")
    page.wait_for_function("() => document.querySelector('#modeSelect').value === 'plan'")
    assert server.store.get_session(session.id).mode == "plan" and model_calls(server) == []
    run(page, "/debug the total is wrong")
    page.wait_for_function("() => document.querySelector('#modeSelect').value === 'debug'")
    page.locator(".msg.user", has_text="the total is wrong").wait_for()
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    assert len(model_calls(server)) == 1 and "/debug" not in str(model_calls(server)[0]["messages"][-1])


def test_model_command(page, server, session):
    open_app(page)
    page.wait_for_function("() => document.querySelectorAll('#tier optgroup').length >= 2")
    run(page, "/model hard")
    page.wait_for_function("() => document.querySelector('#tier').value === 'tier:hard'")
    run(page, "/model opus-5-5")
    page.wait_for_function("() => document.querySelector('#tier').value === 'model:anthropic.claude-opus-5-5'")
    page.wait_for_timeout(200)
    assert server.store.get_session(session.id).model == "anthropic.claude-opus-5-5"


def test_undo_remember_and_export(page, server, session):
    open_app(page)
    run(page, "fix the add bug")
    page.locator("#rbApplyAll").click()
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    page.wait_for_function("() => document.querySelector('#reviewBar').hidden")
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    assert "a + b" in (server.repo / "agent/core.py").read_text()
    run(page, "/undo")
    page.get_by_text("restored").first.wait_for()
    assert "a - b" in (server.repo / "agent/core.py").read_text()

    run(page, "/remember tests need make db-up first")
    page.get_by_text("Saved to this folder's notes").wait_for()
    assert "- tests need make db-up first" in server.store.read_notes(str(server.repo))

    with page.expect_download() as dl:
        run(page, "/export")
    text = open(dl.value.path()).read()
    assert "**You:** fix the add bug" in text and "change #1 to `agent/core.py`" in text


def test_spec_and_report_commands(page, server, session):
    open_app(page)
    run(page, "/spec add CSV export")
    page.locator(".spec-tab .sp-step.current", has_text="Requirements").wait_for()
    assert (server.repo / ".codepilot/specs/csv-export").is_dir()
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    run(page, "/bug")
    page.locator("#reportDialog").wait_for()


def test_paths_and_skills_still_go_to_the_model(page, server, session):
    open_app(page)
    run(page, "/Users/me/app.py fails on import")
    page.locator(".msg.user", has_text="/Users/me/app.py fails").wait_for()
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    assert len(model_calls(server)) == 1


def sent_prompt(page, server, needle):
    page.locator(".msg.user", has_text=needle).wait_for()
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    return str(model_calls(server)[-1]["messages"][-1])


def test_init_drafts_conventions_and_init_foundation_drafts_kiro_docs(page, server, session):
    open_app(page)
    run(page, "/init")
    sent = sent_prompt(page, server, "conventions.md")
    assert "Do not write overviews" in sent and "product.md" not in sent
    run(page, "/init foundation")
    sent = sent_prompt(page, server, "product.md")
    assert "structure.md" in sent and "conventions.md" not in sent
