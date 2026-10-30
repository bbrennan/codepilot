"""Verification receipts: pending changes are tested on a copy before review, and the result shows where you decide."""

import sys
from dataclasses import replace

from uihelpers import open_app


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def receipt_line(page):
    return page.locator("#reviewBar .rb-receipt")


def breaks_when_changed(server):
    """Tests that fail exactly when agent/core.py has the proposed fix, so the receipt reports a new failure."""
    script = "import sys; sys.exit('a + b' in open('agent/core.py').read())"
    server.agent.cfg = replace(server.agent.cfg, test_cmd=f'{sys.executable} -c "{script}"')


def test_pending_changes_can_be_verified_from_the_review_bar(page, server, session):
    open_app(page)
    send(page, "fix the add bug")
    wait_idle(page)
    line = receipt_line(page)
    line.locator("text=not verified").wait_for()
    line.locator("[data-verify]").click()
    line.locator(".ok", has_text="verified").wait_for()
    assert "tests pass" in line.text_content()
    assert "a - b" in (server.repo / "agent/core.py").read_text()  # still only proposed
    page.reload()  # the receipt survives a reload
    receipt_line(page).locator(".ok", has_text="verified").wait_for()


def test_a_receipt_goes_stale_when_the_pending_changes_change(page, server, session):
    open_app(page)
    send(page, "fix two")
    wait_idle(page)
    receipt_line(page).locator("[data-verify]").click()
    receipt_line(page).locator(".ok", has_text="verified").wait_for()
    page.locator(".card[data-prop] [data-reject]").first.click()
    line = receipt_line(page)
    line.locator("text=changed since").wait_for()
    assert line.locator(".ok").count() == 0 and "Re-verify" in line.text_content()


def test_verifying_shows_progress_and_can_be_cancelled(page, server, session):
    open_app(page)
    send(page, "fix the add bug")
    wait_idle(page)
    held = []
    page.route("**/verify", lambda route: held.append(route))
    with page.expect_request("**/verify"):
        receipt_line(page).locator("[data-verify]").click()
    line = receipt_line(page)
    line.locator("text=verifying").wait_for()
    with page.expect_request("**/cancel"):
        line.locator("[data-verify-cancel]").click()
    held[0].continue_()
    wait_idle(page)


def test_the_review_tab_shows_the_receipt(page, server, session):
    open_app(page)
    send(page, "fix the add bug")
    wait_idle(page)
    receipt_line(page).locator("[data-verify]").click()
    receipt_line(page).locator(".ok", has_text="verified").wait_for()
    page.click("#rbReview")
    page.locator(".rv-receipt .rb-receipt .ok", has_text="verified").wait_for()


def test_auto_run_tests_verifies_at_the_end_of_the_turn(page, server, session):
    open_app(page)
    page.check("#autoApprove")
    send(page, "fix the add bug")
    receipt_line(page).locator(".ok", has_text="verified").wait_for()
    card = page.locator("#transcript .card.verify")
    assert card.count() == 1 and "#1" in card.text_content()


def test_a_failing_receipt_explains_and_offers_a_fix(page, server, session):
    breaks_when_changed(server)
    open_app(page)
    send(page, "fix the add bug")
    wait_idle(page)
    line = receipt_line(page)
    line.locator("[data-verify]").click()
    line.locator(".bad", has_text="1 newly failing").wait_for()
    line.locator("[data-receipt-details]").click()
    card = page.locator("#transcript .card.verify").last
    card.locator(".vf-runs").wait_for()
    assert "exit 1" in card.text_content() and "was 0 without the changes" in card.text_content()
    line.locator("[data-receipt-fix]").click()
    page.locator(".msg.user", has_text="newly failing").wait_for()


def test_an_automatic_verification_that_errors_stops_spinning(page, server, session):
    open_app(page)
    send(page, "fix the add bug")  # leaves change #1 waiting
    wait_idle(page)
    page.route("**/chat", lambda route: route.fulfill(  # the next turn ends with a verification that fails to run
        status=200, content_type="application/x-ndjson",
        body='{"type": "verifying", "ids": [1]}\n{"type": "error", "message": "disk full"}\n{"type": "done"}\n'))
    send(page, "carry on")
    page.locator(".banner.error", has_text="disk full").wait_for()
    receipt_line(page).locator("[data-verify]").wait_for()  # back to "not verified", with the button
    assert receipt_line(page).locator(".spinner").count() == 0
