"""Diffs read like a code review tool's: line numbers in two gutters, file names instead of raw `---`/`+++`/`diff --git`
headers, quiet separators between hunks, and the changed file's name shown in full."""

import subprocess

from uihelpers import open_app

ROWS = """() => [...document.querySelectorAll('.review .diff > div')].map((r) => ({
  cls: r.className, text: r.textContent,
  old: r.querySelector('.ln.o')?.textContent.trim() || '', new: r.querySelector('.ln.n')?.textContent.trim() || '' }))"""


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden", timeout=20_000)


def test_the_review_diff_has_line_numbers_and_no_raw_headers(page, server, session):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page)
    send(page, "fix the add bug")
    page.click("#rbReview")
    page.locator(".review .diff").wait_for()
    rows = page.evaluate(ROWS)
    raw = [r["text"] for r in rows if r["text"].lstrip("+- ").startswith(("--- a/", "+++ b/", "@@", "a/", "b/"))
           or r["text"].startswith(("---", "+++", "@@"))]
    assert not raw, f"raw diff headers shown: {raw}"
    by_text = {r["text"].strip(): r for r in rows}
    context = next(r for t, r in by_text.items() if "def add" in t)
    removed = next(r for t, r in by_text.items() if "a - b" in t)
    added = next(r for t, r in by_text.items() if "a + b" in t)
    assert (context["old"], context["new"]) == ("1", "1")
    assert (removed["old"], removed["new"]) == ("2", "") and "d" in removed["cls"].split()
    assert (added["old"], added["new"]) == ("", "2") and "a" in added["cls"].split()
    path = page.locator(".rv-main .crumbs")
    assert "agent/core.py" in path.text_content()
    assert path.evaluate("(el) => el.scrollWidth <= el.clientWidth"), "the file name is cut short"


def test_a_working_tree_diff_names_each_file(page, server, session):
    repo = server.repo
    for args in (["add", "-A"], ["commit", "-qm", "start"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    (repo / "agent" / "core.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "Makefile").write_text("eval-bedrock:\n\techo evals\n")
    open_app(page)
    page.click("[data-view=changes]")
    page.locator("#openGitDiff").click()
    page.locator(".diff").wait_for()
    files = page.locator(".diff .f").all_text_contents()
    assert [f.strip() for f in files] == ["Makefile", "agent/core.py"]
    assert "diff --git" not in page.locator(".diff").text_content() and "index " not in page.locator(".diff").text_content()


def test_a_removed_line_that_starts_with_dashes_is_not_taken_for_a_header(page, server, session):
    open_app(page)
    diff = "--- a/q.sql\n+++ b/q.sql\n@@ -1,2 +1,1 @@\n--- old comment\n select 1;\n"
    rows = page.evaluate("(d) => { const el = document.createElement('div'); el.innerHTML = diffHtml(d); "
                         "return [...el.querySelectorAll('.dl')].map((r) => [r.className, r.textContent]); }", diff)
    assert any("d" in cls.split() and "-- old comment" in text for cls, text in rows), rows
