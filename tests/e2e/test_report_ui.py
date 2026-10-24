"""Help → Report a problem: preview, download, and the pre-filled GitHub issue."""

import json
import urllib.parse

from uihelpers import open_app


def menu(page, label):
    page.locator("#ctxMenu .mi span", has_text=label).click()


def test_report_a_problem(page, server, session):
    page.context.route("https://github.com/**", lambda route: route.fulfill(body="<html>stub</html>"))
    open_app(page)
    page.click("#helpBtn")
    menu(page, "Report a problem")
    page.locator("#reportDialog").wait_for()
    page.fill("#rpTitle", "Boxes reappear")
    page.fill("#rpDesc", "After restarting, old changes come back.")
    page.wait_for_function("() => document.querySelector('#rpPreview').textContent.includes('old changes come back')")
    assert "### Environment" in page.locator("#rpPreview").text_content()

    with page.expect_download() as dl:
        page.click("#rpDownload")
    report = json.loads(open(dl.value.path()).read())
    assert report["environment"]["version"] and report["session"]["id"] == session.id
    assert report["client"]["ui"]["view"] == "explorer"

    with page.context.expect_page() as popup:
        page.click("#rpIssue")
    url = popup.value.url
    assert url.startswith("https://github.com/bbrennan/codepilot/issues/new?")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query["title"] == ["Boxes reappear"] and "old changes come back" in query["body"][0]
    page.keyboard.press("Escape")
    page.locator("#reportDialog").wait_for(state="hidden")


def test_issue_needs_a_title(page, server, session):
    open_app(page)
    page.click("#helpBtn")
    menu(page, "Report a problem")
    page.click("#rpIssue")
    page.get_by_text("Give the issue a short title first.").wait_for()
