"""Spec runs in the chat: "Run all remaining" (or one task's Run) shows its tasks as a card, each ending done, paused
with the reason, or failed, with its test result, and the work its turn did a click away. The card links to the Spec
tab rather than repeating it. The same after a reload, and Retry takes back what the rewound turn did.
(Spec in-chat-progress, task 5: 3.1-3.4.)"""

from test_cost_ui import wait_idle
from uihelpers import open_app

CARD = """() => [...document.querySelectorAll('#transcript .spec-card')].map((c) => ({
  title: c.querySelector(':scope > summary .ttl').textContent,
  live: c.classList.contains('live'),
  items: [...c.querySelectorAll(':scope > .plan-list > .pi')].map((i) => [
    i.querySelector(':scope > summary .t').textContent,
    ['done', 'doing', 'todo', 'paused', 'failed', 'before'].find((s) => i.classList.contains(s)),
    i.querySelector(':scope > summary .note').textContent,
    [...i.querySelectorAll(':scope > .pi-steps details.tool')]
      .map((d) => d.querySelector(':scope > summary .tverb').textContent)]) }))"""

RAN = [
    ["1. Read first", "done", "✓ 1 test passes", ["Read", "Ran the tests", "Marked task 1"]],
    ["2. Left undone", "paused", "not marked done", []],
]


def spec(server, *tasks):
    folder = server.repo / ".codepilot/specs/demo"
    folder.mkdir(parents=True)
    (folder / "requirements.md").write_text("# R\n")
    (folder / "design.md").write_text("# D\n")
    (folder / "tasks.md").write_text("".join(f"- [ ] {i + 1}. {t}\n" for i, t in enumerate(tasks)))
    (folder / "spec.json").write_text('{"kind": "feature", "approved": "tasks"}')


def open_spec(page, server, session, auto_run=True):
    server.store.update_session(session.id, auto_approve=auto_run)  # its tests run without asking
    open_app(page)
    page.click("[data-view=specs]")
    page.locator("[data-spec-open=demo]").click()
    page.locator("#spAll").wait_for()


def cards(page):
    return page.evaluate(CARD)


def test_run_all_shows_each_task_with_how_it_ended_and_its_work(page, server, session):
    spec(server, "Read first", "Left undone")
    open_spec(page, server, session)
    page.click("#spAll")
    # A task in progress spins while its turn runs, before it has done anything.
    task2 = page.locator("#transcript .spec-card .pi.doing", has_text="2. Left undone")
    task2.locator(":scope > summary .spinner").wait_for()
    page.locator("#transcript .spec-card:not(.live)").wait_for()
    wait_idle(page)
    [card] = cards(page)
    assert card["title"] == "Spec demo · paused: task 2 isn't marked done" and card["items"] == RAN
    assert page.locator("#transcript > details.tool").count() == 0  # the steps are in the card, the words in the chat
    page.locator(".msg.assistant", has_text="I couldn't finish this one.").wait_for()

    page.locator("#transcript .spec-card > summary .ttl").click()  # it folded away when the run ended
    item = page.locator("#transcript .spec-card .pi").first
    item.locator(":scope > summary").click()
    assert item.evaluate("(el) => el.open") and item.locator(".pi-steps details.tool").first.is_visible()

    page.reload()
    page.locator("#transcript .spec-card").wait_for()
    assert cards(page) == [card]


def test_one_task_run_is_a_card_too(page, server, session):
    spec(server, "Read first", "Left undone")
    open_spec(page, server, session)
    page.click("#spNext")
    page.locator("#transcript .spec-card.complete").wait_for()
    wait_idle(page)
    [card] = cards(page)
    assert card["title"] == "✓ Spec demo · 1 task done" and card["items"] == RAN[:1]


def test_the_card_links_to_the_spec_tab(page, server, session):
    spec(server, "Read first")
    open_spec(page, server, session)
    page.click("#spNext")
    page.locator("#transcript .spec-card.complete").wait_for()
    wait_idle(page)
    page.locator(".tab.on [data-close]").click()  # close the Spec tab
    page.locator(".spec-tab").wait_for(state="detached")
    card = page.locator("#transcript .spec-card")
    was_open = card.evaluate("(el) => el.open")
    card.locator("[data-spec-open]").click()
    page.locator(".spec-tab .sp-task", has_text="Read first").wait_for()
    assert card.evaluate("(el) => el.open") == was_open  # the link doesn't fold the card


def test_retrying_a_task_takes_back_how_it_ended_and_ends_it_again(page, server, session):
    spec(server, "Read first", "Left undone")
    open_spec(page, server, session)
    page.click("#spAll")
    page.locator("#transcript .spec-card:not(.live)").wait_for()
    wait_idle(page)
    [before] = cards(page)
    msg = page.locator(".msg.user", has_text="Implement task 2")
    msg.hover()
    msg.locator("[data-act=retry]").click()
    page.locator("#transcript .spec-card.live .pi.doing").wait_for()  # task 2 is in progress again
    page.locator("#transcript .spec-card:not(.live)").wait_for()
    wait_idle(page)
    assert cards(page) == [before] and page.locator(".msg.user", has_text="Implement task 2").count() == 1
    page.reload()
    page.locator("#transcript .spec-card").wait_for()
    assert cards(page) == [before]


def test_a_task_waiting_for_your_approval_stays_in_progress_and_carries_on(page, server, session):
    spec(server, "Read first", "Left undone")
    open_spec(page, server, session, auto_run=False)  # running the tests asks first
    page.click("#spAll")
    page.locator("#rbApprove").wait_for()
    wait_idle(page)
    [card] = cards(page)
    assert card["live"] and card["items"][0][1:3] == ["doing", "waiting for your approval"]
    page.click("#rbApprove")
    page.locator("#transcript .spec-card .pi.doing .note", has_text="tests pass").wait_for()  # ran; now, marking it
    page.locator("#rbApprove").wait_for()  # done runs its tests, which asks too
    page.click("#rbApprove")
    page.locator("#transcript .spec-card:not(.live)").wait_for()
    wait_idle(page)
    assert cards(page)[0]["items"] == RAN  # it went on to task 2 once the first was done


def test_a_plan_made_during_a_task_goes_under_that_task(page, server, session):
    spec(server, "Plan first", "Read first")
    open_spec(page, server, session)
    page.click("#spAll")
    page.locator("#transcript .spec-card.complete").wait_for()
    wait_idle(page)
    tasks = page.locator("#transcript .spec-card > .plan-list > .pi")
    plan = tasks.nth(0).locator(".pi-steps .plan-card")
    assert plan.count() == 1 and page.locator("#transcript > .plan-card:not(.spec-card)").count() == 0
    # The plan was left at its step in progress, so the rest of the task's work went under that step.
    assert plan.locator(".pi-steps .tverb").all_text_contents() == ["Read", "Marked task 1"]
    assert tasks.nth(0).locator(":scope > .pi-steps > details.tool").count() == 0
    assert tasks.nth(1).locator(".pi-steps .tverb").all_text_contents() == ["Read", "Ran the tests", "Marked task 2"]


def test_switching_sessions_as_a_run_starts_leaves_the_new_session_alone(page, server, session):
    spec(server, "Read first")
    open_spec(page, server, session)
    held = []
    page.route("**/spec-run", lambda route: route.continue_() if held else held.append(route))  # hold the first
    calls = len(server.llm.calls)
    with page.expect_request("**/spec-run"):
        page.click("#spNext")
    page.click("#newChatBtn")
    page.wait_for_function("() => !document.querySelector('.msg.user')")
    with page.expect_response("**/spec-run"):
        held[0].continue_()
    page.wait_for_timeout(500)
    assert len(server.llm.calls) == calls and page.locator(".msg.user, #transcript .spec-card").count() == 0


def test_a_second_click_while_a_run_starts_runs_nothing_twice(page, server, session):
    spec(server, "Read first", "Left undone")
    open_spec(page, server, session)
    held = []
    page.route("**/spec-run", lambda route: route.continue_() if held else held.append(route))  # hold the first
    with page.expect_request("**/spec-run"):
        page.click("#spNext")
    page.click("#spNext")
    page.wait_for_timeout(300)
    for route in held:
        route.continue_()
    page.locator("#transcript .spec-card.complete").wait_for()
    wait_idle(page)
    assert len(held) == 1 and len(cards(page)) == 1
    assert page.locator(".msg.user", has_text="Implement task").count() == 1


def test_reloading_during_a_task_still_ends_it(page, server, session):
    spec(server, "Read first", "Left undone")
    open_spec(page, server, session)
    page.click("#spAll")
    page.locator("#transcript .spec-card .pi.doing", has_text="2. Left undone").wait_for()
    page.reload()  # task 2 is still running: the page follows it
    page.locator("#transcript .spec-card:not(.live)").wait_for()
    wait_idle(page)
    [card] = cards(page)
    assert card["items"] == RAN and card["title"] == "Spec demo · paused: task 2 isn't marked done"
    page.reload()
    page.locator("#transcript .spec-card").wait_for()
    assert cards(page) == [card]


def test_approving_while_the_last_turn_is_still_settling_lets_the_task_finish(page, server, session):
    spec(server, "Read first slowly", "Left undone")
    open_spec(page, server, session, auto_run=False)
    held, hold = [], [True]
    page.route("**/specs", lambda route: held.append(route) if hold[0] and route.request.method == "GET"
               else route.continue_())
    page.click("#spAll")
    page.locator("#rbApprove").wait_for()
    wait_idle(page)
    hold[0] = False
    for route in held[:-1]:
        route.continue_()  # the last is the turn's: it settles after you approve
    page.click("#rbApprove")
    page.locator("#stopBtn").wait_for()  # the approved work is running
    held[-1].continue_()
    page.locator("#rbApprove").wait_for()  # marking it done runs its tests: that asks too
    wait_idle(page)
    assert cards(page)[0]["items"][0][1:3] == ["doing", "waiting for your approval · tests pass"]
    page.click("#rbApprove")
    page.locator("#transcript .spec-card:not(.live)").wait_for()
    wait_idle(page)
    assert [i[1] for i in cards(page)[0]["items"]] == ["done", "paused"]


def test_a_retried_task_shows_the_verification_its_turn_made(page, server, session):
    spec(server, "Change first")
    open_spec(page, server, session)  # auto-run tests: pending changes are verified when a turn ends
    page.click("#spNext")
    page.locator("#reviewBar .rb-receipt .ok").wait_for()
    wait_idle(page)
    # Its changes wait for your review, so it can't be marked done yet: the verification of them is its result.
    assert cards(page)[0]["items"][0][1:3] == ["doing", "waiting for your review · ✓ verified"]
    msg = page.locator(".msg.user", has_text="Implement task 1")
    msg.hover()
    msg.locator("[data-act=retry]").click()
    if page.locator("#dialog").is_visible():
        page.click("#dialogOk")
    page.locator("#transcript .spec-card.live .pi.doing").wait_for()
    page.locator("#reviewBar .rb-receipt .ok").wait_for()  # the retried turn's changes, verified
    wait_idle(page)
    assert cards(page)[0]["items"][0][1:3] == ["doing", "waiting for your review · ✓ verified"]


def test_a_task_done_without_tests_says_why(page, server, session):
    spec(server, "Write the docs")  # the scripted model marks it done as having nothing to test
    open_spec(page, server, session)
    page.click("#spNext")
    page.locator("#transcript .spec-card.complete").wait_for()
    wait_idle(page)
    assert cards(page)[0]["items"][0][1:3] == ["done", "not tested: a scripted task"]
    assert "  - _Tests: none (a scripted task)_" in (server.repo / ".codepilot/specs/demo/tasks.md").read_text()
