"""Read-only steps in a row fold into one row that says what they did ("Read 3 files, searched twice") and expands to
the steps. An error never folds, and splits the run; anything else between two reads (codepilot's words, a change) does
too. The same live and after a reload. (Spec in-chat-progress, task 3: criteria 1.3, 1.4.)"""

from test_readable_steps_ui import send
from uihelpers import open_app

TOP_ROWS = """() => [...document.querySelectorAll('#transcript > details.tool')].map((d) => {
  const steps = d.querySelectorAll(':scope > .group-steps > details.tool');
  return (d.querySelector(':scope > summary .tverb').textContent + ' ' + d.querySelector(':scope > summary .targ').textContent).trim()
    + (steps.length ? ` [${steps.length}]` : '') + (d.querySelector(':scope > summary .st.err') ? ' (error)' : '');
})"""


def top_rows(page):
    return page.evaluate(TOP_ROWS)


def call(id_, name, **args):
    return f"render({{ type: 'tool_call', id: '{id_}', name: '{name}', input: {args!r} }});"


def result(id_, name, error=False):
    out = "boom" if error else "ok"
    return f"render({{ type: 'tool_result', id: '{id_}', name: '{name}', output: '{out}', is_error: {str(error).lower()} }});"


def test_seven_reads_show_as_one_row_that_opens_to_the_seven(page, server, session):
    open_app(page)
    send(page, "long task")
    assert top_rows(page) == ["Read agent/core.py 7 times [7]"]
    group = page.locator("#transcript > details.step-group")
    assert not group.evaluate("d => d.open")
    group.locator(":scope > summary").click()
    assert group.locator(".group-steps > details.tool").nth(6).is_visible()
    page.reload()
    page.locator("#transcript > details.step-group").wait_for()
    assert top_rows(page) == ["Read agent/core.py 7 times [7]"]


def test_the_row_says_what_the_steps_did(page, server, session):
    open_app(page)
    page.evaluate("() => {" + "".join(
        call(f"r{i}", "read_file", path=p) + result(f"r{i}", "read_file") for i, p in enumerate(["a.py", "b.py", "c.py"]))
        + "".join(call(f"s{i}", "search_code", pattern=p) + result(f"s{i}", "search_code") for i, p in enumerate("xy"))
        + "}")
    assert top_rows(page) == ["Read 3 files, searched twice [5]"]


def test_an_error_between_reads_splits_the_group(page, server, session):
    open_app(page)
    one_by_one = "".join(call(f"r{i}", "read_file", path=f"{i}.py") + result(f"r{i}", "read_file", error=i == 2)
                         for i in range(1, 6))
    page.evaluate("() => {" + one_by_one + "}")
    expected = ["Read 1.py", "Read 2.py (error)", "Read 3 files [3]"]
    assert top_rows(page) == expected


def test_an_error_among_reads_made_at_once_splits_the_group_too(page, server, session):
    # Several calls in one reply: the steps arrive first, their results after, so the group exists when the error does.
    open_app(page)
    calls = "".join(call(f"r{i}", "read_file", path=f"{i}.py") for i in range(1, 6))
    results = "".join(result(f"r{i}", "read_file", error=i == 2) for i in range(1, 6))
    page.evaluate("() => {" + calls + "}")
    assert top_rows(page) == ["Read 5 files [5]"]
    status = "() => [...document.querySelectorAll('#transcript > .step-group > summary .st')].map((s) => s.className)"
    assert page.evaluate(status) == ["st"]  # spinning while its steps run
    page.evaluate("() => {" + results + "}")
    assert top_rows(page) == ["Read 1.py", "Read 2.py (error)", "Read 3 files [3]"]
    assert page.evaluate(status) == ["st ok"]


def test_words_between_reads_keep_them_apart(page, server, session):
    open_app(page)
    page.evaluate("() => {" + call("r1", "read_file", path="a.py") + result("r1", "read_file")
                  + "render({ type: 'assistant', text: 'Now the other one.' });"
                  + call("r2", "read_file", path="b.py") + result("r2", "read_file") + "}")
    assert top_rows(page) == ["Read a.py", "Read b.py"]


def test_a_reply_with_words_between_its_reads_looks_the_same_after_a_reload(page, server, session):
    # Live, a reply's words stream before any of its steps is drawn; a reload must keep that order, not the stored one.
    open_app(page)
    send(page, "read, explain, read")
    shown = "() => [...document.querySelectorAll('#transcript > *')].map((e) => e.className.split(' ')[0])"
    live, rows = page.evaluate(shown), top_rows(page)
    assert rows == ["Read 2 files [2]"]
    page.reload()
    page.locator("#transcript > details.tool").first.wait_for()
    page.locator(".msg.assistant", has_text="Done.").wait_for()
    assert (page.evaluate(shown), top_rows(page)) == (live, rows)


def test_one_file_spelled_two_ways_is_one_file(page, server, session):
    open_app(page)
    root = page.evaluate("state.workspace")
    spellings = ["agent/core.py", "./agent/core.py", f"{root}/agent/core.py", " agent/../agent/core.py"]
    page.evaluate("() => {" + "".join(call(f"r{i}", "read_file", path=p) + result(f"r{i}", "read_file")
                                      for i, p in enumerate(spellings)) + "}")
    assert top_rows(page) == ["Read agent/core.py 4 times [4]"]
