"""The plan checklist: pinned while it's live, kept in the transcript once it's done or replaced, the same after a
reload."""

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
    assert page.locator("#plan .it.done", has_text="Write tests").count() == 1
    assert "✓ Write tests" in page.locator(".tool", has_text="update_plan").last.text_content()
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
    assert "0 of 2" in head(page) and page.locator("#plan .it", has_text="Profile the query").count() == 1
    card = page.locator("#transcript .plan-card", has_text="Plan replaced")
    assert card.count() == 1 and "1 of 2 done" in card.text_content()
    card.locator("summary").click()
    assert card.locator(".it", has_text="Implement export").count() == 1  # the unfinished step stays visible
    page.reload()
    page.locator("#transcript .plan-card", has_text="Plan replaced").wait_for()
    assert "Profile the query" in page.locator("#plan").text_content()


def test_the_plan_collapses_to_its_header(page, server, session):
    open_app(page)
    send(page, "plan start")
    page.click("#plan .plan-head")
    assert page.locator("#plan .plan-items").is_hidden() and "0 of 2" in head(page)
    send(page, "plan progress")
    assert page.locator("#plan .plan-items").is_hidden() and "1 of 2" in head(page)  # stays collapsed
    page.click("#plan .plan-head")
    assert page.locator("#plan .plan-items").is_visible()


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
    assert "Write tests" in page.locator("#plan").text_content() and "0 of 2" in head(page)


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


def test_the_plan_header_works_from_the_keyboard(page, server, session):
    open_app(page)
    send(page, "plan start")
    toggle = page.locator("#plan .plan-head")
    assert toggle.get_attribute("role") == "button" and toggle.get_attribute("aria-expanded") == "true"
    toggle.focus()
    page.keyboard.press("Enter")
    assert page.locator("#plan .plan-items").is_hidden()
    assert page.locator("#plan .plan-head").get_attribute("aria-expanded") == "false"
    assert page.evaluate("document.activeElement.classList.contains('plan-head')")  # focus survives the re-render
    page.keyboard.press(" ")
    assert page.locator("#plan .plan-items").is_visible()
