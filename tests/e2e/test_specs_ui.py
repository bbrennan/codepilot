"""Spec-driven development in the UI: create, review and approve each phase, then run tasks."""

from uihelpers import open_app


def answer(page, text):
    page.locator("#dialog").wait_for()
    page.fill("#dialogInput", text)
    page.press("#dialogInput", "Enter")


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def approve(page, label):
    btn = page.locator("#spApprove", has_text=label)
    btn.wait_for()
    btn.click()


def test_full_spec_flow(page, server, session):
    open_app(page)
    page.click("[data-view=specs]")
    page.click("#specNew")
    answer(page, "Add CSV export to reports")
    page.locator("#dialogTitle", has_text="Spec name").wait_for()
    assert page.input_value("#dialogInput") == "csv-export-reports"
    page.press("#dialogInput", "Enter")
    page.locator(".spec-tab .sp-step.current", has_text="Requirements").wait_for()
    wait_idle(page)
    page.locator(".sp-doc", has_text="WHEN the user clicks Export").wait_for()  # written by codepilot, rendered
    folder = server.repo / ".codepilot/specs/csv-export-reports"
    assert (folder / "requirements.md").exists()
    assert page.evaluate("document.querySelector('#modeSelect').value") == "spec"

    approve(page, "Approve requirements")
    page.locator(".sp-step.current", has_text="Design").wait_for()
    wait_idle(page)
    page.locator(".sp-doc", has_text="write_csv function").wait_for()
    approve(page, "Approve design")
    wait_idle(page)
    page.locator(".sp-doc", has_text="Add write_csv").wait_for()
    approve(page, "Approve tasks")
    page.locator(".sp-step.current", has_text="Implement").wait_for()
    page.locator(".sp-task", has_text="Add write_csv").wait_for()
    assert page.locator(".sp-task.done").count() == 0

    page.click("#spNext")
    page.locator(".sp-task.done", has_text="Add write_csv").wait_for()
    wait_idle(page)
    assert "- [x] 1. Add write_csv" in (folder / "tasks.md").read_text()
    page.click("#spAll")
    page.locator(".sp-bar .status.applied", has_text="complete").wait_for()
    assert (folder / "tasks.md").read_text().count("- [x]") == 2


def test_spec_mode_message_starts_a_spec(page, server, session):
    open_app(page)
    page.select_option("#modeSelect", "spec")
    page.fill("#input", "Add a dark mode toggle")
    page.press("#input", "Enter")
    page.locator(".spec-chip", has_text="started spec").wait_for()
    page.locator(".spec-tab .sp-step.current", has_text="Requirements").wait_for()
    wait_idle(page)
    assert (server.repo / ".codepilot/specs/dark-mode-toggle/requirements.md").exists()


def test_ask_for_changes_and_edit(page, server, session):
    open_app(page)
    page.click("[data-view=specs]")
    page.click("#specNewBug")
    answer(page, "Checkout total is wrong with discounts")
    page.press("#dialogInput", "Enter")
    page.locator(".sp-step.current", has_text="Bug analysis").wait_for()
    page.locator(".sp-doc", has_text="WHEN the user clicks Export").wait_for()
    page.locator("#spAsk").fill("mention the rounding mode")
    page.press("#spAsk", "Enter")
    page.locator(".msg.user", has_text="About the bug analysis of spec").wait_for()
    wait_idle(page)
    page.click("#spEdit")
    page.locator("#codeEdit").wait_for()
    assert page.locator(".tab.on .label").text_content() == "bugfix.md"


def test_the_specs_view_lists_only_codepilot_specs(page, server, session):
    for folder, doc in ((".kiro/specs/kiro-thing", "requirements.md"), ("specs/001-speckit-thing", "spec.md"),
                        (".codepilot/specs/mine", "requirements.md")):
        (server.repo / folder).mkdir(parents=True)
        (server.repo / folder / doc).write_text("# Requirements\n")
    open_app(page)
    page.click("[data-view=specs]")
    page.locator("#specsView [data-spec-open='mine']").wait_for()
    names = page.locator("#specsView [data-spec-open]").evaluate_all("els => els.map((e) => e.dataset.specOpen)")
    assert names == ["mine"]
