"""The plan as a card in the chat: its steps with their status, each with the work done under it, a click away. The
step in progress spins only while codepilot works; the pinned plan is one line that takes you to the card. The same
after a reload, and Edit takes the rewound work back out of the card. (Spec in-chat-progress, task 4: 2.1–2.4.)"""

from test_plan_ui import head, send, wait_idle
from uihelpers import open_app

CARD = """() => [...document.querySelectorAll('#transcript .plan-card')].map((c) => ({
  title: c.querySelector(':scope > summary').textContent.replace(/\\s+/g, ' ').trim(),
  live: c.classList.contains('live'),
  groups: [...c.querySelectorAll(':scope .pi')].map((i) => [
    i.querySelector(':scope > summary .t').textContent,
    ['done', 'doing', 'todo', 'before'].find((s) => i.classList.contains(s)),
    [...i.querySelectorAll(':scope > .pi-steps details.tool')].map((d) => d.querySelector(':scope > summary .tverb').textContent
      + ' ' + d.querySelector(':scope > summary .targ').textContent)]) }))"""

WORKED = [
    ["Before the plan", "before", ["Read tests/test_core.py"]],
    ["Write tests", "done", ["Searched for def add"]],
    ["Implement export", "doing", ["Read Makefile"]],
]


def cards(page):
    return page.evaluate(CARD)


def top_steps(page):
    return page.locator("#transcript > details.tool .tverb").all_text_contents()


def test_a_plan_is_a_card_with_the_work_filed_under_each_step(page, server, session):
    open_app(page)
    page.fill("#input", "plan and work")
    page.press("#input", "Enter")
    page.locator("#transcript .plan-card .pi.doing > summary .spinner").wait_for()  # step 2 is being worked on
    wait_idle(page)
    assert page.locator("#transcript .plan-card .spinner").count() == 0  # the turn ended: nothing spins
    [card] = cards(page)
    assert card["live"] and "1 of 2 done" in card["title"]
    assert card["groups"] == WORKED
    assert top_steps(page) == ["Read"]  # the read before the plan existed stays in the chat
    assert page.locator("#transcript details.tool", has_text="Updated the plan").count() == 0  # the card says it
    item = page.locator("#transcript .pi", has_text="Write tests")
    assert not item.evaluate("d => d.open")
    item.locator(":scope > summary").click()
    assert item.locator(".pi-steps details.tool").is_visible()

    page.reload()
    page.locator("#transcript .plan-card .pi").first.wait_for()
    page.locator(".msg.assistant", has_text="Done.").wait_for()
    assert cards(page) == [card] and top_steps(page) == ["Read"]


def test_the_pinned_plan_is_one_line_that_takes_you_to_the_card(page, server, session):
    page.set_viewport_size({"width": 1200, "height": 560})
    open_app(page)
    send(page, "plan and work")
    for _ in range(3):
        send(page, "hello")  # the card scrolls out of sight
    assert "Paused at step 2 of 2" in head(page) and "1 of 2 done" in head(page)
    assert page.locator("#plan .it, #plan .plan-items").count() == 0  # one line: the steps are in the card
    card = page.locator("#transcript .plan-card")
    item = card.locator(".pi.doing")
    assert not card.evaluate(IN_VIEW) and not item.evaluate("d => d.open")
    page.click("#plan .plan-head")
    page.wait_for_function(f"() => ({IN_VIEW})(document.querySelector('#transcript .plan-card .pi.doing'))")
    assert item.evaluate("d => d.open")  # the step in progress, opened


def test_the_pinned_line_works_from_the_keyboard(page, server, session):
    page.set_viewport_size({"width": 1200, "height": 560})
    open_app(page)
    send(page, "plan and work")
    for _ in range(3):
        send(page, "hello")
    toggle = page.locator("#plan .plan-head")
    assert toggle.get_attribute("role") == "button"
    toggle.focus()
    page.keyboard.press("Enter")
    page.wait_for_function(f"() => ({IN_VIEW})(document.querySelector('#transcript .plan-card .pi.doing'))")


def test_editing_a_message_takes_its_work_back_out_of_the_card(page, server, session):
    open_app(page)
    send(page, "plan and work")
    send(page, "fix it")  # a change, filed under step 2
    step2 = page.locator("#transcript .plan-card .pi.doing .pi-steps")
    assert step2.locator(".card.prop").count() == 1 and page.locator("#transcript > .card.prop").count() == 0
    msg = page.locator(".msg.user", has_text="fix it")
    msg.hover()
    msg.locator("[data-act=edit]").click()
    msg.locator(".edit-box textarea").fill("just say hi")
    msg.locator(".edit-box textarea").press("Enter")
    page.locator(".msg.user", has_text="just say hi").wait_for()
    wait_idle(page)
    assert cards(page)[0]["groups"] == WORKED and step2.locator(".card.prop").count() == 0


def test_editing_away_a_new_plan_brings_the_old_card_back(page, server, session):
    open_app(page)
    send(page, "plan and work")
    send(page, "plan other")
    before, after = cards(page)
    assert not before["live"] and "Plan replaced" in before["title"] and after["live"]
    msg = page.locator(".msg.user", has_text="plan other")
    msg.hover()
    msg.locator("[data-act=edit]").click()
    msg.locator(".edit-box textarea").fill("just say hi")
    msg.locator(".edit-box textarea").press("Enter")
    page.locator(".msg.user", has_text="just say hi").wait_for()
    wait_idle(page)
    [card] = cards(page)
    assert card["live"] and "Plan replaced" not in card["title"] and card["groups"] == WORKED
    assert "Paused at step 2 of 2" in head(page)


def test_a_dismissed_plan_keeps_its_work_after_a_reload(page, server, session):
    # You dismiss a plan after its turn ends, so the work after its last update is in the card; a reload agrees.
    open_app(page)
    send(page, "plan and work")
    page.click("#planDismiss")
    page.wait_for_function("() => document.querySelector('#plan').hidden")
    [card] = cards(page)
    assert not card["live"] and "Plan dismissed" in card["title"] and card["groups"] == WORKED
    page.reload()
    page.locator("#transcript .plan-card .pi").first.wait_for(state="attached")  # folded away, as it was
    page.locator(".msg.assistant", has_text="Done.").wait_for()
    assert cards(page) == [card] and top_steps(page) == ["Read"]


IN_VIEW = """(el) => { const r = el.getBoundingClientRect(), t = document.querySelector('#transcript').getBoundingClientRect();
  return r.top >= t.top - 1 && r.top < t.bottom - 10; }"""
