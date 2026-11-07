"""Diffs read like a code review tool's: line numbers in two gutters, file names instead of raw `---`/`+++`/`diff --git`
headers, quiet separators between hunks, and the changed file's name shown in full."""

import subprocess

from uihelpers import open_app

ROWS = """() => [...document.querySelectorAll('.review .diff > div')].map((r) => ({
  cls: r.className, text: r.textContent,
  old: r.querySelector('.ln.o')?.textContent.trim() || '',
  new: r.querySelector('.ln.n')?.textContent.trim() || '' }))"""


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
    (repo / "café.py").write_text("x = 1\n")
    (repo / "my notes.txt").write_text("one\n")  # git ends its ---/+++ lines with a tab for names with spaces
    for args in (["add", "-A"], ["commit", "-qm", "start"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    (repo / "agent" / "core.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "Makefile").write_text("eval-bedrock:\n\techo evals\n")
    (repo / "café.py").write_text("x = 2\n")  # git quotes this name: "b/caf\303\251.py"
    (repo / "my notes.txt").write_text("two\n")
    open_app(page)
    page.click("[data-view=changes]")
    page.locator("#openGitDiff").click()
    page.locator(".diff").wait_for()
    files = page.locator(".diff .f").all_text_contents()
    assert files == ["Makefile", "agent/core.py", "café.py", "my notes.txt"]  # exactly: no trailing tab
    text = page.locator(".diff").text_content()
    assert "diff --git" not in text and "index " not in text


def test_a_removed_line_that_starts_with_dashes_is_not_taken_for_a_header(page, server, session):
    open_app(page)
    diff = "--- a/q.sql\n+++ b/q.sql\n@@ -1,2 +1,1 @@\n--- old comment\n select 1;\n"
    rows = page.evaluate("(d) => { const el = document.createElement('div'); el.innerHTML = diffHtml(d); "
                         "return [...el.querySelectorAll('.dl')].map((r) => [r.className, r.textContent]); }", diff)
    assert any("d" in cls.split() and "-- old comment" in text for cls, text in rows), rows


def test_every_kind_of_change_is_named_and_explained(page, server, session):
    """Quoted names (git's C-quoting of non-ASCII paths), mode-only, binary and renamed files: each gets its name and a
    plain description, and none of their headers turn into numbered code rows."""
    open_app(page)
    diff = "\n".join([
        "diff --git a/agent/core.py b/agent/core.py", "index 1111111..2222222 100644",
        "--- a/agent/core.py", "+++ b/agent/core.py", "@@ -1 +1 @@", "-a", "+b",
        'diff --git "a/caf\\303\\251.py" "b/caf\\303\\251.py"', "index 3333333..4444444 100644",
        '--- "a/caf\\303\\251.py"', '+++ "b/caf\\303\\251.py"', "@@ -1 +1 @@", "-x = 1", "+x = 2",
        "diff --git a/run.sh b/run.sh", "old mode 100644", "new mode 100755",
        "diff --git a/logo.png b/logo.png", "index 5555555..6666666 100644",
        "Binary files a/logo.png and b/logo.png differ",
        "diff --git a/old_name.py b/new_name.py", "similarity index 100%", "rename from old_name.py",
        "rename to new_name.py", ""])
    seen = page.evaluate("""(d) => { const el = document.createElement('div'); el.innerHTML = diffHtml(d);
      return { files: [...el.querySelectorAll('.f')].map((r) => r.textContent),
               meta: [...el.querySelectorAll('.meta')].map((r) => r.textContent),
               code: [...el.querySelectorAll('.dl .code')].map((r) => r.textContent) }; }""", diff)
    assert seen["files"] == ["agent/core.py", "café.py", "run.sh", "logo.png", "new_name.py"]
    assert any("100644 → 100755" in m for m in seen["meta"]) and any("binary" in m.lower() for m in seen["meta"])
    assert any("renamed from old_name.py" in m for m in seen["meta"])
    assert sorted(seen["code"]) == ["a", "b", "x = 1", "x = 2"], seen["code"]  # only real lines are numbered


def test_a_long_path_keeps_the_review_buttons_in_reach(page, server, session):
    from codepilot import tools
    long = "src/very/deeply/nested/package/module_with_a_rather_long_name/implementation_details_and_helpers.py"
    ctx = tools.ToolContext(root=server.repo.resolve(), cfg=server.cfg, store=server.store, session_id=session.id)
    tools.propose_edit(ctx, long, "", "x = 1\n")
    page.set_viewport_size({"width": 1280, "height": 800})
    open_app(page)
    page.click("#rbReview")
    page.locator(".rv-main .crumbs").wait_for()
    pane = page.locator(".rv-main").bounding_box()
    for sel in ("[data-apply]", "[data-reject]", "#rvOpen"):
        box = page.locator(f".rv-main .ed-bar {sel}").bounding_box()
        assert box and box["x"] + box["width"] <= pane["x"] + pane["width"] + 0.5, f"{sel} is pushed out of reach"
    assert long in page.locator(".rv-main .crumbs").text_content()


def _rows(page, diff):
    return page.evaluate("""(d) => { const el = document.createElement('div'); el.innerHTML = diffHtml(d);
      return { files: [...el.querySelectorAll('.f')].map((r) => r.textContent),
               lines: [...el.querySelectorAll('.dl')].map((r) => [r.className, r.querySelector('.code').textContent]),
               hunks: el.querySelectorAll('.hunk').length,
               meta: [...el.querySelectorAll('.meta')].map((r) => r.textContent) }; }""",
        diff)


def test_file_names_with_spaces_are_shown_as_they_are(page, server, session):
    open_app(page)
    seen = _rows(page, "\n".join([
        "diff --git a/my notes.txt b/my notes.txt", "index 1..2 100644", "--- a/my notes.txt", "+++ b/my notes.txt",
        "@@ -1 +1 @@", "-old", "+new",
        "diff --git a/old name.txt b/new name.txt", "similarity index 90%", "rename from old name.txt",
        "rename to new name.txt", ""]))
    assert seen["files"] == ["my notes.txt", "new name.txt"], seen


def test_a_merge_in_progress_shows_its_combined_diff(page, server, session):
    """During an unresolved merge, `git diff` gives a combined diff; its changes must show, not an empty view."""
    open_app(page)
    seen = _rows(page, "\n".join([
        "diff --cc agent/core.py", "index 1111111,2222222..0000000", "--- a/agent/core.py", "+++ b/agent/core.py",
        "@@@ -1,2 -1,2 +1,6 @@@", "  def add(a, b):", "++<<<<<<< HEAD", " +    return a + b", "++=======",
        "+     return b + a", "++>>>>>>> other", ""]))
    assert seen["files"] == ["agent/core.py"], seen
    texts = [t for _, t in seen["lines"]]
    assert "<<<<<<< HEAD" in texts and "    return a + b" in texts and "def add(a, b):" in texts, texts
    assert any("merge" in m.lower() for m in seen["meta"]), seen["meta"]


def test_every_form_of_file_header_names_the_right_file(page, server, session):
    """Mixed quoting in renames (git quotes each side on its own), and a path that itself contains " b/"."""
    open_app(page)
    headers = {
        'diff --git "a/caf\\303\\251.py" b/cafe.py': "cafe.py",  # quoted source, plain destination
        'diff --git a/old name.txt "b/caf\\303\\251.py"': "café.py",  # plain source with a space, quoted destination
        "diff --git a/docs b/file.txt b/docs b/file.txt": "docs b/file.txt",  # " b/" inside the path itself
        "diff --git a/my notes.txt b/my notes.txt": "my notes.txt",
    }
    for header, name in headers.items():
        seen = _rows(page, header + "\n")
        assert seen["files"] == [name], (header, seen["files"])


def test_rename_sources_and_unusual_names_come_out_as_written(page, server, session):
    open_app(page)
    # A rename whose source contains " b/": the "rename to" line, not the header, says which file it is.
    seen = _rows(page, "\n".join(["diff --git a/docs b/old.txt b/docs b/new.txt", "similarity index 100%",
                                    "rename from docs b/old.txt", "rename to docs b/new.txt", ""]))
    assert seen["files"] == ["docs b/new.txt"] and seen["meta"] == ["renamed from docs b/old.txt"], seen
    # Git quotes the source of a rename too.
    seen = _rows(page, "\n".join(['diff --git "a/caf\\303\\251.py" b/cafe.py', "similarity index 100%",
                                    'rename from "caf\\303\\251.py"', "rename to cafe.py", ""]))
    assert seen["files"] == ["cafe.py"] and seen["meta"] == ["renamed from café.py"], seen
    # With core.quotePath=false, Unicode stays literal inside quotes; only the tab is escaped.
    seen = _rows(page, 'diff --git "a/x\\t😀.txt" "b/x\\t😀.txt"\n')
    assert seen["files"] == ["x\t😀.txt"], seen
