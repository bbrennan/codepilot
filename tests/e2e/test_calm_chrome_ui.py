"""Quiet chrome: nothing on screen that's empty, raw or alarming when all is well. The bottom panel waits until you open
it, the welcome page fits a folder that's already open, and the status bar is short and calm."""

from uihelpers import open_app


def test_the_bottom_panel_waits_until_you_open_it_and_then_stays(page, server, session):
    open_app(page)
    assert page.locator("#panel").is_hidden()  # first run: no empty "Activity 0" panel
    page.click("#togglePanel")
    assert page.locator("#panel").is_visible()
    page.reload()
    page.locator("#sbProvider").wait_for()
    page.wait_for_function("() => !document.querySelector('#ide').classList.contains('no-panel')")  # your choice sticks


def test_the_welcome_page_fits_a_folder_thats_already_open(page, server, session):
    open_app(page)
    welcome = page.locator(".welcome")
    assert "Working in" in welcome.text_content() and "target" in welcome.text_content()
    assert "Open a folder, then" not in welcome.text_content()
    assert page.locator("#wOpen").text_content().strip() == "Open another folder…"


def test_the_status_bar_is_short_and_calm(page, server, session):
    open_app(page)
    test_cmd = page.locator("#sbTest")
    assert len(test_cmd.text_content().strip()) <= 26 and "tests-ran" in (test_cmd.get_attribute("title") or "")
    github = page.locator("#sbGithub")
    github.wait_for()
    color = github.evaluate("(el) => getComputedStyle(el.firstElementChild || el).color")
    muted = page.evaluate("() => getComputedStyle(document.querySelector('.statusbar')).color")
    assert color == muted, f"github status is coloured like a warning: {color}"
    page.fill("#input", "hello")
    page.press("#input", "Enter")
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden", timeout=20_000)
    ctx = page.locator("#ctxText").text_content()
    assert ctx.startswith("context ") and "/" not in ctx  # the numbers are on hover
    assert "/" in page.locator("#sbContext").get_attribute("title") or "budget" in page.locator("#sbContext").get_attribute("title")
