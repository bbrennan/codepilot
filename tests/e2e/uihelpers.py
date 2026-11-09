"""Helpers for the browser tests."""


def open_app(page, wait_tree=True):
    # A first visit shows Sessions; these tests start from the Explorer, as someone who has chosen it would.
    # (try: about:blank, which some tests visit, has no storage)
    page.add_init_script("try { localStorage.getItem('cp-view') ?? localStorage.setItem('cp-view', 'explorer') } catch {}")
    page.goto("/")
    page.wait_for_function("() => document.querySelector('#sbProvider')?.textContent.length > 0")
    if wait_tree:
        page.locator("#tree [data-file], #tree [data-dir]").first.wait_for()
    return page
