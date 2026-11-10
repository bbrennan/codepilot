"""Progress in its own view: a plan's or spec run's card lives in the sidebar's Progress view, with one line in the chat
where it started, so it doesn't scroll away while the conversation goes on (spec progress-view). The activity-bar icon
counts while it's live, and the sidebar switches to it once per card."""

from test_plan_ui import send, wait_idle
from uihelpers import open_app

VIEW = ".sidebar .view[data-view=progress]"


def test_a_plan_lives_in_progress_with_a_line_in_the_chat(page, server, session):
    open_app(page)
    send(page, "plan and work")
    assert page.locator("#transcript .plan-card").count() == 0  # out of the chat
    card = page.locator("#progressList > .plan-card")
    assert card.count() == 1 and card.locator(".pi").count() == 3  # before the plan, and its two steps
    assert card.locator(".pi.doing .pi-steps details.tool").count() == 1  # with the work done under each
    mark = page.locator("#transcript .progress-mark")
    assert mark.count() == 1 and "Plan" in mark.text_content() and "1 of 2 done" in mark.text_content()
    assert page.locator("#transcript > details.tool .tverb").all_text_contents() == ["Read"]  # before the plan

    page.reload()
    page.locator("#progressList > .plan-card .pi").first.wait_for(state="attached")
    assert page.locator("#progressList > .plan-card").count() == 1
    assert "1 of 2 done" in page.locator("#transcript .progress-mark").text_content()


def test_the_line_says_how_the_plan_ended(page, server, session):
    open_app(page)
    send(page, "plan start")
    send(page, "plan finish")
    assert "Plan complete" in page.locator("#transcript .progress-mark").text_content()
    assert page.locator("#progressList > .plan-card.complete").count() == 1


def test_the_sidebar_switches_to_progress_once_per_plan(page, server, session):
    open_app(page)  # (on the Explorer)
    send(page, "plan start")
    assert page.locator(VIEW).is_visible()
    page.click("[data-view=explorer]")
    send(page, "plan progress")  # the same plan, further on: you chose the Explorer, so it stays
    assert page.locator(VIEW).is_hidden()
    page.reload()  # replaying doesn't switch either
    page.locator("#progressList > .plan-card").wait_for(state="attached")
    assert page.locator(VIEW).is_hidden()


def test_the_icon_counts_while_a_plan_is_live(page, server, session):
    open_app(page)
    badge = page.locator("#progressBadge")
    assert badge.is_hidden()
    send(page, "plan start")
    assert badge.text_content() == "0/2"
    send(page, "plan progress")
    assert badge.text_content() == "1/2"
    send(page, "plan finish")
    assert badge.is_hidden()


def test_the_line_and_the_pinned_plan_open_the_view_at_the_card(page, server, session):
    open_app(page)
    send(page, "plan and work")
    page.click("[data-view=explorer]")
    page.locator("#transcript .progress-mark [data-progress-open]").click()
    assert page.locator(VIEW).is_visible()
    doing = page.locator("#progressList > .plan-card > .plan-list > .pi.doing")
    assert doing.evaluate("(d) => d.open && d.closest('.plan-card').open")
    page.click("[data-view=explorer]")
    page.click("#plan .plan-head")
    assert page.locator(VIEW).is_visible()


def test_a_change_filed_under_a_step_opens_from_the_view(page, server, session):
    open_app(page)
    send(page, "plan and work")
    send(page, "fix it")  # a change, filed under step 2
    change = page.locator("#progressList .pi.doing .pi-steps .card.prop")
    assert change.count() == 1 and page.locator("#transcript .card.prop").count() == 0
    page.locator("#progressList .pi.doing > summary").click()  # unfold step 2
    change.locator("[data-prop-open]").click()  # the chat's click handler works in the view too
    page.locator("#editorTabs .tab", has_text="Review").wait_for()


def test_editing_away_the_message_that_made_a_plan_takes_its_card_away(page, server, session):
    open_app(page)
    send(page, "hello")
    send(page, "plan start")
    msg = page.locator(".msg.user", has_text="plan start")
    msg.hover()
    msg.locator("[data-act=edit]").click()
    msg.locator(".edit-box textarea").fill("just say hi")
    msg.locator(".edit-box textarea").press("Enter")
    page.locator(".msg.user", has_text="just say hi").wait_for()
    wait_idle(page)
    assert page.locator("#progressList .plan-card").count() == 0
    assert page.locator("#transcript .progress-mark").count() == 0
    page.locator("#progressList .progress-empty").wait_for(state="attached")


def test_each_session_shows_its_own_progress(page, server, session):
    open_app(page)
    page.click("[data-view=progress]")
    assert page.locator("#progressList .progress-empty").is_visible()  # nothing yet: it says what will show
    send(page, "plan start")
    assert page.locator("#progressList .progress-empty").is_hidden()
    page.click("#newChatBtn")
    page.wait_for_function("() => document.querySelectorAll('#sessionList .session').length === 2")
    page.locator("#progressList .progress-empty").wait_for()
    assert page.locator("#progressList .plan-card").count() == 0 and page.locator("#progressBadge").is_hidden()
    page.click("#chatTitleBtn")
    page.locator(f"#sessPop .sess-opt[data-id='{session.id}']").click()
    page.locator("#progressList > .plan-card").wait_for()
