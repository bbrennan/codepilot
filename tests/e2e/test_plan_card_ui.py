"""The plan as a card (in Progress since spec progress-view): its steps with their status, each with the work done
under it, a click away. The step in progress spins only while codepilot works; the pinned plan is one line that takes
you to the card. The same after a reload, and Edit takes the rewound work back out of the card. (Spec
in-chat-progress, task 4: 2.1–2.4.)"""

from test_plan_ui import head, send, wait_idle
from uihelpers import open_app

CARD = """() => [...document.querySelectorAll('#progressList .plan-card')].map((c) => ({
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
    page.locator("#progressList .plan-card .pi.doing > summary .spinner").wait_for()  # step 2 is being worked on
    wait_idle(page)
    assert page.locator("#progressList .plan-card .spinner").count() == 0  # the turn ended: nothing spins
    [card] = cards(page)
    assert card["live"] and "1 of 2 done" in card["title"]
    assert card["groups"] == WORKED
    assert top_steps(page) == ["Read"]  # the read before the plan existed stays in the chat
    assert page.locator("#transcript details.tool", has_text="Updated the plan").count() == 0  # the card says it
    item = page.locator("#progressList .pi", has_text="Write tests")
    assert not item.evaluate("d => d.open")
    item.locator(":scope > summary").click()
    assert item.locator(".pi-steps details.tool").is_visible()

    page.reload()
    page.locator("#progressList .plan-card .pi").first.wait_for()
    page.locator(".msg.assistant", has_text="Done.").wait_for()
    assert cards(page) == [card] and top_steps(page) == ["Read"]


def test_the_pinned_plan_is_one_line_that_takes_you_to_the_card(page, server, session):
    page.set_viewport_size({"width": 1200, "height": 560})
    open_app(page)
    send(page, "plan and work")
    for _ in range(3):
        send(page, "hello")  # the conversation goes on
    page.click("[data-view=explorer]")  # and you look at the files
    assert "Paused at step 2 of 2" in head(page) and "1 of 2 done" in head(page)
    assert page.locator("#plan .it, #plan .plan-items").count() == 0  # one line: the steps are in the card
    card = page.locator("#progressList .plan-card")
    item = card.locator(".pi.doing")
    assert not card.evaluate(IN_VIEW) and not item.evaluate("d => d.open")
    page.click("#plan .plan-head")
    page.wait_for_function(f"() => ({IN_VIEW})(document.querySelector('#progressList .plan-card .pi.doing'))")
    assert item.evaluate("d => d.open")  # the step in progress, opened


def test_the_pinned_line_works_from_the_keyboard(page, server, session):
    page.set_viewport_size({"width": 1200, "height": 560})
    open_app(page)
    send(page, "plan and work")
    for _ in range(3):
        send(page, "hello")
    page.click("[data-view=explorer]")
    toggle = page.locator("#plan .plan-head")
    assert toggle.get_attribute("role") == "button"
    toggle.focus()
    page.keyboard.press("Enter")
    page.wait_for_function(f"() => ({IN_VIEW})(document.querySelector('#progressList .plan-card .pi.doing'))")


def test_editing_a_message_takes_its_work_back_out_of_the_card(page, server, session):
    open_app(page)
    send(page, "plan and work")
    send(page, "fix it")  # a change, filed under step 2
    step2 = page.locator("#progressList .plan-card .pi.doing .pi-steps")
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
    after, before = cards(page)  # newest first
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
    page.locator("#progressList .plan-card .pi").first.wait_for(state="attached")  # folded away, as it was
    page.locator(".msg.assistant", has_text="Done.").wait_for()
    assert cards(page) == [card] and top_steps(page) == ["Read"]


IN_VIEW = """(el) => { const r = el.getBoundingClientRect(), t = document.querySelector('#progressList').getBoundingClientRect();
  return r.top >= t.top - 1 && r.top < t.bottom - 10; }"""


# -- review fixes ------------------------------------------------------------------------------------------------------

def _plan(items, kind="new"):
    """A plan event as the server sends it."""
    done = sum(i["status"] == "done" for i in items)
    return f"render({{ type: 'plan', kind: '{kind}', items: {items!r}, progress: [{done}, {len(items)}], changes: [], retired: null }});"


def _read(id_, path):
    return (f"render({{ type: 'tool_call', id: '{id_}', name: 'read_file', input: {{ path: '{path}' }} }});"
            f"render({{ type: 'tool_result', id: '{id_}', name: 'read_file', output: 'ok', is_error: false }});")


def test_words_between_reads_keep_them_apart_inside_a_step_too(page, server, session):
    open_app(page)
    page.evaluate("() => {" + _plan([{"text": "Look", "status": "doing"}])
                  + _read("r1", "a.py") + "render({ type: 'assistant', text: 'Now b.' });" + _read("r2", "b.py")
                  + "render({ type: 'user', text: 'and c and d' });" + _read("r3", "c.py") + _read("r4", "d.py") + "}")
    rows = page.locator("#progressList .pi.doing > .pi-steps > details.tool > summary .tverb").all_text_contents()
    assert rows == ["Read", "Read", "Read 2 files"]  # c and d, with nothing between them, still fold


def test_steps_with_the_same_name_stay_one_row_each(page, server, session):
    open_app(page)
    twice = [{"text": "Run tests", "status": "todo"}, {"text": "Fix it", "status": "doing"},
             {"text": "Run tests", "status": "todo"}]
    later = [{"text": "Run tests", "status": "done"}, {"text": "Fix it", "status": "done"},
             {"text": "Run tests", "status": "doing"}]
    page.evaluate("() => {" + _plan(twice) + _plan(later, "update") + _plan(later, "update") + "}")
    assert page.locator("#progressList .plan-card .pi.it").all_text_contents() == ["Run tests", "Fix it", "Run tests"]
    page.evaluate("() => {" + _read("r1", "a.py") + "}")  # filed under the second "Run tests", the one in progress
    assert page.locator("#progressList .pi.it").nth(2).locator(".pi-steps details.tool").count() == 1


def test_after_editing_away_the_turn_a_step_started_in_work_goes_before_the_plan(page, server, session):
    open_app(page)
    send(page, "plan start")  # all to do
    send(page, "plan progress")  # step 2 in progress
    msg = page.locator(".msg.user", has_text="plan progress")
    msg.hover()
    msg.locator("[data-act=edit]").click()
    msg.locator(".edit-box textarea").fill("slow tool please")  # a read, while no step has started
    msg.locator(".edit-box textarea").press("Enter")
    page.locator(".msg.user", has_text="slow tool please").wait_for()
    wait_idle(page)
    [card] = cards(page)
    assert card["groups"][0] == ["Before the plan", "before", ["Read agent/core.py"]], card["groups"]


def test_the_paused_plan_and_its_buttons_share_one_line(page, server, session):
    open_app(page)
    send(page, "plan progress")
    box = lambda sel: page.locator(sel).bounding_box()  # noqa: E731
    head, cont = box("#plan .plan-head"), box("#planContinue")
    assert abs((head["y"] + head["height"] / 2) - (cont["y"] + cont["height"] / 2)) < 6, (head, cont)
    page.click("#plan .plan-head")  # the line still takes you to the card, and the buttons still work
    page.click("#planContinue")
    page.locator(".msg.user", has_text='next is step 2, "Implement export"').wait_for()


def test_editing_a_later_turn_keeps_a_dismissed_plan_dismissed(page, server, session):
    # Dismissed after a later turn; editing that turn leaves the dismissal standing (the server says no plan is live).
    open_app(page)
    send(page, "plan and work")
    send(page, "slow tool please")
    page.click("#planDismiss")
    page.wait_for_function("() => document.querySelector('#plan').hidden")
    msg = page.locator(".msg.user", has_text="slow tool please")
    msg.hover()
    msg.locator("[data-act=edit]").click()
    msg.locator(".edit-box textarea").fill("just say hi")
    msg.locator(".edit-box textarea").press("Enter")
    page.locator(".msg.user", has_text="just say hi").wait_for()
    wait_idle(page)
    [card] = cards(page)
    assert not card["live"] and "Plan dismissed" in card["title"] and page.locator("#plan").is_hidden()


def test_each_step_says_its_status_to_a_screen_reader(page, server, session):
    open_app(page)
    send(page, "plan and work")
    marks = page.locator("#progressList .plan-card .pi > summary .mk")
    said = marks.evaluate_all("els => els.map((e) => [e.getAttribute('role'), e.getAttribute('aria-label')])")
    assert said == [["img", "Before any step"], ["img", "Done"], ["img", "In progress"]]
