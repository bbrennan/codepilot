"""Each step in the chat says what it did in plain words ("Read agent/core.py", "Ran the tests"), with the tool's name
and arguments one click away; the same live and after a reload. (Spec in-chat-progress, task 1: criteria 1.1, 1.4.)"""

import re

from uihelpers import open_app

ROWS = """() => [...document.querySelectorAll('#transcript details.tool')].map((d) => ({
  summary: [d.querySelector('.tverb')?.textContent, d.querySelector('.targ')?.textContent].filter(Boolean).join(' ').trim(),
  raw: d.querySelector('.traw')?.textContent || '', open: d.open }))"""


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")
    page.locator(".msg.user", has_text=text).last.wait_for()
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden", timeout=20_000)


def summaries(page):
    return page.evaluate(ROWS)


def test_steps_read_as_plain_words_with_the_tool_one_click_away(page, server, session):
    open_app(page)
    send(page, "plan progress")  # update_plan
    send(page, "slow tool please")  # read_file
    send(page, "run python please")  # run_command, waiting for approval
    rows = summaries(page)
    said = [r["summary"] for r in rows]
    assert any(s.startswith("Updated the plan") and "1 of 2" in s for s in said), said
    assert any(s.startswith("Read agent/core.py") for s in said), said
    assert any(s.startswith("Ran python -c") for s in said), said
    for r in rows:
        assert not re.search(r"\b(update_plan|read_file|run_command)\b", r["summary"]), r  # no tool names up front
        assert r["raw"] and not r["open"]  # but there, folded away: the name and the arguments
    assert any("read_file" in r["raw"] and '"path": "agent/core.py"' in r["raw"] for r in rows)


def test_a_tool_without_a_phrasing_still_reads_sensibly(page, server, session):
    open_app(page)
    page.evaluate("""() => render({ type: 'tool_call', id: 'x1', name: 'mystery_tool', input: { thing: 'widget' } })""")
    row = summaries(page)[-1]
    assert row["summary"].startswith("Used mystery_tool"), row


def test_a_reload_shows_the_same_steps(page, server, session):
    open_app(page)
    send(page, "plan progress")
    send(page, "slow tool please")
    live = [r["summary"] for r in summaries(page)]
    page.reload()
    page.locator("#transcript details.tool").first.wait_for()
    page.wait_for_function("(n) => document.querySelectorAll('#transcript details.tool').length >= n", arg=len(live))
    assert [r["summary"] for r in summaries(page)] == live


def test_a_read_from_a_line_does_not_claim_the_rest_of_the_file(page, server, session):
    # read_file without end_line reads a window (500 lines), not the rest of the file: "lines 100–end" would overstate it.
    open_app(page)
    page.evaluate("""() => {
      render({ type: 'tool_call', id: 'r1', name: 'read_file', input: { path: 'large.py', start_line: 100 } });
      render({ type: 'tool_call', id: 'r2', name: 'read_file', input: { path: 'large.py', start_line: 5, end_line: 9 } });
    }""")
    said = [r["summary"] for r in summaries(page)[-2:]]
    assert said == ["Read large.py from line 100", "Read large.py lines 5–9"], said
