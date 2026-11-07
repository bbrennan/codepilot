"""The plan checklist: a card in the chat, with a one-line summary pinned while it's live; the card stays in the
transcript once the plan is done or replaced, the same after a reload. (The card itself: test_plan_card_ui.py.)"""

from uihelpers import open_app


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")
    page.locator(".msg.user", has_text=text).last.wait_for()
    wait_idle(page)


def head(page):
    return page.locator("#plan .plan-head").text_content()


def test_a_plan_is_pinned_while_live_then_kept_in_the_transcript(page, server, session):
    open_app(page)
    send(page, "plan start")
    assert "Plan" in head(page) and "0 of 2" in head(page)
    send(page, "plan progress")
    assert "1 of 2" in head(page)
    assert page.locator("#transcript .plan-card.live .it.done", has_text="Write tests").count() == 1
    assert page.locator("#transcript details.tool", has_text="Updated the plan").count() == 0  # the card says it
    send(page, "plan finish")
    assert "Plan complete" in head(page)
    card = page.locator("#transcript .plan-card")
    assert card.count() == 1 and "Plan complete" in card.text_content() and "2 of 2" in card.text_content()
    send(page, "thanks")
    assert page.locator("#plan").is_hidden()  # done: it lives in the transcript now
    page.reload()
    page.locator("#transcript .plan-card", has_text="Plan complete").wait_for()
    assert page.locator("#plan").is_hidden()


def test_a_new_plan_retires_the_old_one_without_losing_it(page, server, session):
    open_app(page)
    send(page, "plan start")
    send(page, "plan progress")
    send(page, "plan other")
    assert "0 of 2" in head(page)
    assert page.locator("#transcript .plan-card.live .it", has_text="Profile the query").count() == 1
    card = page.locator("#transcript .plan-card", has_text="Plan replaced")
    assert card.count() == 1 and "1 of 2 done" in card.text_content()
    card.locator(":scope > summary").click()
    assert card.locator(".it", has_text="Implement export").count() == 1  # the unfinished step stays visible
    page.reload()
    page.locator("#transcript .plan-card", has_text="Plan replaced").wait_for()
    assert "Profile the query" in page.locator("#transcript .plan-card.live").text_content()


def test_editing_an_earlier_message_brings_back_the_plan_from_then(page, server, session):
    open_app(page)
    send(page, "plan start")
    send(page, "plan other")
    msg = page.locator(".msg.user", has_text="plan other")
    msg.hover()
    msg.locator("[data-act=edit]").click()
    msg.locator(".edit-box textarea").fill("just say hi")
    msg.locator(".edit-box textarea").press("Enter")
    page.locator(".msg.user", has_text="just say hi").wait_for()
    wait_idle(page)
    assert "Write tests" in page.locator("#transcript .plan-card.live").text_content() and "0 of 2" in head(page)


def test_editing_after_a_plan_finished_keeps_it_out_of_the_way(page, server, session):
    open_app(page)
    send(page, "plan start")
    send(page, "plan finish")
    send(page, "thanks")
    assert page.locator("#plan").is_hidden()
    msg = page.locator(".msg.user", has_text="thanks")
    msg.hover()
    msg.locator("[data-act=edit]").click()
    msg.locator(".edit-box textarea").fill("thanks again")
    msg.locator(".edit-box textarea").press("Enter")
    page.locator(".msg.user", has_text="thanks again").wait_for()
    wait_idle(page)
    assert page.locator("#plan").is_hidden() and page.locator("#transcript .plan-card.complete").count() == 1


# -- the plan says what's really happening ---------------------------------------------------------------------------


def test_the_step_in_progress_spins_only_while_codepilot_works(page, server, session):
    open_app(page)
    page.fill("#input", "plan slowly")
    page.press("#input", "Enter")
    page.locator("#transcript .plan-card .it.doing > summary .spinner").wait_for()  # working on step 2
    assert "Paused" not in head(page)
    wait_idle(page)
    assert page.locator("#transcript .plan-card .spinner").count() == 0  # the turn ended: nothing is spinning
    assert "Paused at step 2 of 2" in head(page) and "1 of 2 done" in head(page)
    assert page.locator("#planContinue").is_visible() and page.locator("#planDismiss").is_visible()


def test_continue_carries_on_from_the_next_step(page, server, session):
    open_app(page)
    send(page, "plan progress")
    page.click("#planContinue")
    page.locator(".msg.user", has_text='next is step 2, "Implement export"').wait_for()


def test_dismiss_puts_a_paused_plan_away_and_codepilot_is_told(page, server, session):
    open_app(page)
    send(page, "plan progress")
    page.click("#planDismiss")
    page.wait_for_function("() => document.querySelector('#plan').hidden")
    card = page.locator("#transcript .plan-card", has_text="Plan dismissed")
    assert card.count() == 1 and "1 of 2 done" in card.text_content()
    page.reload()
    page.locator("#transcript .plan-card", has_text="Plan dismissed").wait_for()
    assert page.locator("#plan").is_hidden()  # still put away after a reload
    send(page, "thanks")
    told = server.llm.calls[-1]["messages"][-1]["content"]
    assert any("dismissed your plan" in b.get("text", "") for b in told)


def test_a_plan_waiting_on_an_approval_says_so(page, server, session):
    open_app(page)
    send(page, "a long command please")  # a plan, then a command waiting for approval
    page.locator("#reviewBar .rb-approval").wait_for()
    assert "Waiting for your approval" in head(page) and page.locator("#planContinue").count() == 0
