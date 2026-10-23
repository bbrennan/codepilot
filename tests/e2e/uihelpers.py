"""Helpers for the browser tests."""


def open_app(page, wait_tree=True):
    page.goto("/")
    page.wait_for_function("() => document.querySelector('#sbProvider')?.textContent.length > 0")
    if wait_tree:
        page.locator("#tree [data-file], #tree [data-dir]").first.wait_for()
    return page
