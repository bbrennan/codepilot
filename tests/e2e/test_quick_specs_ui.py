"""Quick specs: one review, then build. Also the length hint and task reminders."""

import json

from test_specs_ui import answer, wait_idle
from uihelpers import open_app


def start_quick(page):
    page.click("[data-view=specs]")
    page.click("#specQuick")
    answer(page, "Add CSV export to reports")
    page.locator("#dialogTitle", has_text="Spec name").wait_for()
    page.press("#dialogInput", "Enter")
    page.locator(".spec-tab .sp-step.current", has_text="Plan").wait_for()
    wait_idle(page)


def spec_on_disk(server, name, approved="", tasks=None, requirements=None):
    folder = server.repo / ".codepilot/specs" / name
    folder.mkdir(parents=True)
    (folder / "spec.json").write_text(json.dumps({"kind": "feature", "approved": approved}))
    (folder / "requirements.md").write_text(requirements or "# R\n\n1.1 WHEN x THEN y SHALL z.\n")
    (folder / "design.md").write_text("# D\n")
    if tasks:
        (folder / "tasks.md").write_text(tasks)


def test_quick_spec_is_one_review_then_implement(page, server, session):
    open_app(page)
    start_quick(page)
    assert page.locator(".sp-steps .sp-step").all_text_contents() == ["1Plan", "2Implement"]
    assert page.locator(".sp-sub .sp-step").all_text_contents() == ["Requirements", "Design", "Tasks"]
    page.locator(".sp-doc", has_text="WHEN the user clicks Export").wait_for()
    page.click(".sp-sub [data-sp-view=design]")
    page.locator(".sp-doc", has_text="write_csv function").wait_for()
    page.click(".sp-sub [data-sp-view=tasks]")
    page.locator(".sp-doc", has_text="Add write_csv").wait_for()
    page.locator("#spApprove").wait_for(state="detached")  # one button for the whole plan

    page.click("#spApprovePlan")
    page.locator(".sp-step.current", has_text="Implement").wait_for()
    page.locator(".sp-task", has_text="Add write_csv").wait_for()
    assert page.locator(".spec-row .incl", has_text="quick").count() == 1
    page.click(".sp-steps .sp-step >> text=Plan")  # the plan stays readable, but it's done with
    page.locator(".sp-doc", has_text="WHEN the user clicks Export").wait_for()
    assert page.locator("#spApprovePlan, #spToFull").count() == 0


def test_a_slow_document_cant_replace_the_one_you_moved_to(page, server, session):
    open_app(page)
    start_quick(page)
    held = []
    page.route("**/files?path=*design.md", lambda route: held.append(route))
    with page.expect_request("**/files?path=*design.md"):
        page.click(".sp-sub [data-sp-view=design]")
    page.click(".sp-sub [data-sp-view=tasks]")
    page.locator(".sp-doc", has_text="Add write_csv").wait_for()
    with page.expect_response("**/files?path=*design.md"):
        held[0].continue_()
    page.wait_for_timeout(200)
    assert "Add write_csv" in page.locator(".sp-doc").text_content()


def test_switching_to_full_review_keeps_the_documents(page, server, session):
    open_app(page)
    start_quick(page)
    calls = len(server.llm.calls)
    page.click("#spToFull")
    page.locator(".sp-step.current", has_text="Requirements").wait_for()
    assert page.locator(".sp-steps .sp-step").count() == 4
    page.click("#spApprove")
    page.locator(".sp-step.current", has_text="Design").wait_for()
    page.locator(".sp-doc", has_text="write_csv function").wait_for()  # what the plan already said
    page.wait_for_timeout(300)
    assert len(server.llm.calls) == calls  # kept, not written again


def test_spec_command_starts_a_quick_spec(page, server, session):
    open_app(page)
    page.fill("#input", "/spec quick add csv export")
    page.press("#input", "Enter")
    page.locator(".spec-tab .sp-step.current", has_text="Plan").wait_for()
    wait_idle(page)
    assert json.loads((server.repo / ".codepilot/specs/csv-export/spec.json").read_text())["profile"] == "quick"
    assert (server.repo / ".codepilot/specs/csv-export/tasks.md").exists()


def test_a_long_document_gets_a_quiet_hint(page, server, session):
    spec_on_disk(server, "long", requirements="line\n" * 250)
    spec_on_disk(server, "short")
    open_app(page)
    page.click("[data-view=specs]")
    page.click("[data-spec-open=long]")
    hint = page.locator(".sp-long")
    hint.wait_for()
    assert "250 lines" in hint.text_content() and "consider trimming or splitting" in hint.text_content()
    assert page.locator("#spApprove").is_enabled()  # a hint, not a gate
    page.click("[data-spec-open=short]")
    page.locator(".sp-doc", has_text="WHEN x").wait_for()
    assert hint.count() == 0


def test_a_reminder_shows_in_activity_only(page, server, session):
    spec_on_disk(server, "long-run", approved="tasks", tasks="- [-] 1. Keep going\n  - _Requirements: 1.1_\n")
    open_app(page)
    page.click("[data-view=specs]")
    page.click("[data-spec-open=long-run]")
    page.locator(".sp-task").first.wait_for()
    page.evaluate("ensureSpecActive(findSpec('long-run'))")
    page.wait_for_function("() => state.specs.active === 'long-run'")
    page.fill("#input", "long task")
    page.press("#input", "Enter")
    wait_idle(page)
    page.locator(".act", has_text="reminder: task 1").wait_for()
    assert page.locator(".act", has_text="reminder: task 1").count() == 1
    assert "spec_reminder" in str(server.llm.calls[-1]["messages"])

    def in_chat():
        return page.evaluate("document.querySelector('#transcript').textContent.includes('spec_reminder')")

    assert not in_chat()
    page.reload()
    page.locator(".msg.user", has_text="long task").wait_for()
    assert not in_chat()
