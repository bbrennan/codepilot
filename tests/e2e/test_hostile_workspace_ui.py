"""A messy real-world workspace must not break the explorer or the viewer: odd names, binary and huge files, loops."""

import os

import pytest

from uihelpers import open_app

NAMES = ['<img src=x onerror="window.__xss=1">.txt', "it's \"quoted\".txt", "emoji 😀 é ☃.txt", "back\\slash.txt", "a b  c.txt",
         "#hash&amp;.txt", "%41.txt", "-dash.txt", ".hidden-file", "x" * 200 + ".txt"]


def hostile(repo):
    for n in NAMES:
        (repo / n).write_text(f"content of {n[:20]}\n")
    (repo / "binary.bin").write_bytes(bytes(range(256)) * 50)
    (repo / "empty.txt").write_text("")
    (repo / "huge.txt").write_text("line of text\n" * 400_000)  # ~5 MB
    os.symlink(repo, repo / "loop")
    os.symlink(repo / "nowhere", repo / "dangling")
    deep = repo
    for i in range(25):
        deep = deep / f"d{i}"
    deep.mkdir(parents=True)
    (deep / "bottom.txt").write_text("deep")
    many = repo / "many"
    many.mkdir()
    for i in range(400):
        (many / f"f{i:03}.txt").write_text(str(i))


def test_odd_names_render_as_text_never_as_markup(page, server, session):
    hostile(server.repo)
    open_app(page)
    assert page.locator("#tree .row").count() >= len(NAMES)
    assert page.evaluate("window.__xss") is None
    assert page.locator("#tree img").count() == 0  # the <img> name is text, not an element
    page.locator("#tree .row", has_text="emoji 😀").click()
    page.locator(".code-view", has_text="content of emoji").wait_for()
    page.locator("#tree .row", has_text="quoted").click()
    page.locator(".code-view", has_text="content of it's").wait_for()
    page.locator("#tree .row", has_text="#hash").click()
    page.locator(".code-view", has_text="content of #hash").wait_for()


@pytest.mark.parametrize("name", ["empty.txt", "binary.bin", "huge.txt", "dangling", "loop"])
def test_binary_empty_huge_and_looping_files_do_not_break_the_viewer(page, server, session, name):
    hostile(server.repo)
    page.expected_errors.extend(["Failed to load resource", "415", "413"])
    open_app(page)
    page.locator("#tree .row", has_text=name).first.click()
    page.wait_for_timeout(1500)
    assert page.locator("#tree .row").count() > 5, f"explorer broke after opening {name}"
    assert page.evaluate("document.querySelector('#editor').innerText.length") > 0, name


def test_deep_nesting_and_many_siblings(page, server, session):
    hostile(server.repo)
    open_app(page)
    page.locator("#tree .row", has_text="many").first.click()
    page.locator("#tree .row", has_text="f399.txt").wait_for()
    page.locator("#tree .row", has_text="d0").first.click()
    for i in range(1, 25):
        page.locator("#tree .row", has_text=f"d{i}").first.click()
    page.locator("#tree .row", has_text="bottom.txt").wait_for()
    page.locator("#tree .row", has_text="bottom.txt").click()
    page.locator(".code-view", has_text="deep").wait_for()
