"""Package guard: what the public registry says shows where you decide."""

import pytest
from uihelpers import open_app

from codepilot import deps_guard


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


@pytest.fixture
def nothing_on_pypi(monkeypatch):
    def get(url, timeout):
        raise deps_guard.NotFound

    monkeypatch.setattr(deps_guard, "_get", get)


def test_a_new_dependency_is_flagged_on_its_change(page, server, session, nothing_on_pypi):
    open_app(page)
    send(page, "add a dependency")
    page.locator(".card[data-prop] .dep-mark").wait_for()  # flagged on its line in the chat
    wait_idle(page)
    page.click("#rbReview")
    line = page.locator(".dep-advice .dep.danger")
    line.wait_for()
    assert "reqeusts" in line.text_content() and "not on PyPI" in line.text_content()
    assert page.locator(".rv-item .dep-mark").count() == 1
    page.reload()  # kept with the change
    page.locator(".card[data-prop] .dep-mark").wait_for()


def test_an_install_shows_the_registry_on_the_approval_and_offers_no_rule(page, server, session, nothing_on_pypi):
    open_app(page)
    send(page, "install a package")
    warning = page.locator("#reviewBar .rb-warn.danger")
    warning.wait_for()
    assert "reqeusts: not on PyPI" in warning.text_content() and page.locator("#rbAllow").count() == 0
    page.click("#rbDeny")


def test_a_change_with_no_new_dependency_has_no_mark(page, server, session):
    open_app(page)
    send(page, "fix the add bug")
    page.locator(".card[data-prop]").wait_for()
    wait_idle(page)
    assert page.locator(".dep-mark").count() == 0
