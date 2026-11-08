"""Each change shows once in the chat: the change's own row (file, +/− counts, Apply/Reject) takes the place of the step
that proposed it, and a spec document written shows as its "Wrote …" step, not also as a chip. The same after a reload.
(Spec in-chat-progress, task 2: criteria 1.2, 1.4.)"""

from test_quick_specs_ui import start_quick
from test_readable_steps_ui import send, summaries
from uihelpers import open_app


def rows_in_order(page):
    """What the chat shows, top to bottom: steps by their words, changes by their file."""
    return page.evaluate("""() => [...document.querySelectorAll('#transcript details.tool, #transcript .card.prop')]
      .map((e) => e.matches('.tool') ? 'step: ' + e.querySelector('.tverb').textContent
                                    : 'change: ' + e.querySelector('.path').textContent)""")


def test_two_changes_show_as_two_change_rows_and_no_proposing_steps(page, server, session):
    open_app(page)
    send(page, "fix two things")
    expected = ["change: agent/core.py", "change: tests/test_core.py"]
    assert rows_in_order(page) == expected
    page.reload()
    page.locator("#transcript .card.prop").nth(1).wait_for()
    assert rows_in_order(page) == expected


def test_a_change_that_could_not_be_made_keeps_its_step_with_the_error(page, server, session):
    open_app(page)
    page.evaluate("""() => {
      render({ type: 'tool_call', id: 'e1', name: 'propose_edit', input: { path: 'x.py', old_text: 'nope', new_text: 'y' } });
      render({ type: 'tool_result', id: 'e1', name: 'propose_edit', output: 'old_text not found in file', is_error: true });
    }""")
    row = summaries(page)[-1]
    assert row["summary"].startswith("Proposed a change to x.py"), row
    assert page.locator("#transcript details.tool .st.err").count() == 1


def test_a_quick_spec_shows_its_documents_as_steps_without_chips(page, server, session):
    open_app(page)
    start_quick(page)
    said = [r["summary"] for r in summaries(page)]
    wrote = [s for s in said if s.startswith("Wrote ")]
    assert [w.split(" · ")[0] for w in wrote] == ["Wrote requirements.md", "Wrote design.md", "Wrote tasks.md"], said
    assert page.locator("#transcript .spec-chip").count() == 0
    page.reload()
    page.locator("#transcript details.tool").nth(2).wait_for()
    assert [r["summary"] for r in summaries(page)] == said
    assert page.locator("#transcript .spec-chip").count() == 0


def test_what_the_checks_found_after_an_auto_apply_moves_into_the_change_row(page, server, session):
    # The step folds away, but its result can say more than the change row does: keep that in the change row.
    open_app(page)
    page.evaluate("""() => {
      render({ type: 'tool_call', id: 'a1', name: 'propose_edit', input: { path: 'x.py', old_text: 'a', new_text: 'b' } });
      render({ type: 'proposal', proposal: { id: 41, path: 'x.py', status: 'applied', reason: '', diff: '', advice: [] } });
      render({ type: 'tool_result', id: 'a1', name: 'propose_edit', is_error: false,
               output: 'Applied change #41 to x.py (auto-apply is on; the user can undo it).\\n'
                       + 'Automatic checks on the file found:\\nx.py:1: E501 line too long' });
    }""")
    assert rows_in_order(page)[-1] == "change: x.py"
    note = page.locator("#transcript .card.prop[data-prop='41'] .step-note")
    assert "E501 line too long" in note.text_content() and "Applied change" not in note.text_content()


def test_spec_steps_have_the_specs_icon(page, server, session):
    open_app(page)
    start_quick(page)
    specs_icon = page.locator("[data-view=specs] svg").first.inner_html()
    wrote = page.locator("#transcript details.tool", has=page.locator(".tverb", has_text="Wrote"))
    assert wrote.count() == 3
    assert {wrote.nth(i).locator(".ticon svg").inner_html() for i in range(3)} == {specs_icon}
    page.evaluate("""() => render({ type: 'tool_call', id: 'u1', name: 'update_task', input: { task: '1', status: 'done' } })""")
    assert page.locator("#transcript details.tool").last.locator(".ticon svg").inner_html() == specs_icon
