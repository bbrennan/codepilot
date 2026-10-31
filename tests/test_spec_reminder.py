"""Reminding the agent of its task during a long implementation turn."""

from fakes import FakeLLM, tool_use

from codepilot import spec_reminder, specs
from codepilot.agent import Agent, history_events
from codepilot.context import _is_user_turn

REQUIREMENTS = """# Requirements

## 1. Export

1.1 WHEN the user clicks Export
THEN the system SHALL download a CSV file.
1.2 The file SHALL have a header.

- 2.1 IF it fails THEN the system SHALL say so.
**2.2** Bold is fine too.

## 3. Other
"""


def spec_with(root, tasks, requirements=REQUIREMENTS):
    spec = specs.create(root, "export")
    spec.doc("requirements").write_text(requirements)
    spec.doc("design").write_text("# Design\n")
    spec.doc("tasks").write_text(tasks)
    return specs.approve(root, specs.approve(root, specs.approve(root, spec, "requirements"), "design"), "tasks")


def test_due_every_sixth_step():
    assert [s for s in range(1, 13) if spec_reminder.due(s)] == [6, 12]


def test_criteria_are_found_across_wrapped_lines_and_styles():
    found = spec_reminder.criteria(REQUIREMENTS, ["1.1", "2.1", "2.2", "9.9"])
    assert found == {"1.1": "WHEN the user clicks Export THEN the system SHALL download a CSV file.",
                     "2.1": "IF it fails THEN the system SHALL say so.", "2.2": "Bold is fine too."}


def test_a_criterion_stops_at_a_heading():
    assert spec_reminder.criteria("1.1 One.\n\n## 2. Next\n", ["1.1"]) == {"1.1": "One."}


def test_the_reminder_names_the_task_and_its_criteria(repo):
    spec = spec_with(repo, "- [-] 2. Add write_csv\n  - _Requirements: 1.1, 1.2_\n- [ ] 3. Later\n")
    text = spec_reminder.text(spec)
    assert text.startswith('<spec_reminder spec="export" task="2">') and text.endswith("</spec_reminder>")
    assert "2: Add write_csv" in text and "1.1 WHEN the user clicks Export" in text and "1.2 The file" in text
    assert "don't start the next" in text and "Later" not in text


def test_the_innermost_task_in_progress_is_the_current_one(repo):
    spec = spec_with(repo, "- [-] 1. Parent\n  - [x] 1.1 Done\n  - [-] 1.2 This one\n  - [ ] 1.3 Next\n")
    assert spec_reminder.current(spec).id == "1.2"


def test_no_matching_criteria_leaves_the_task_alone(repo):
    spec = spec_with(repo, "- [-] 1. Task\n  - _Requirements: 9.9_\n")
    assert "1: Task" in spec_reminder.text(spec) and "Criteria" not in spec_reminder.text(spec)


def test_no_task_in_progress_means_no_reminder(repo):
    assert spec_reminder.text(spec_with(repo, "- [ ] 1. Task\n- [x] 2. Done\n")) is None


def test_a_reminder_stays_short(repo):
    long = "# R\n\n" + "".join(f"1.{i} {'WHEN it is very long ' * 40}\n" for i in range(1, 9))
    refs = ", ".join(f"1.{i}" for i in range(1, 9))
    spec = spec_with(repo, f"- [-] 1. {'Long title ' * 60}\n  - _Requirements: {refs}_\n", long)
    text = spec_reminder.text(spec)
    assert len(text) <= spec_reminder.MAX_CHARS and text.endswith("</spec_reminder>")


def long_turn(repo, store, cfg, tasks, steps=12, mode="spec"):
    from dataclasses import replace
    spec_with(repo, tasks)
    llm = FakeLLM([[tool_use(f"t{i}", "read_file", path="x.py")] for i in range(steps)] + [[{"text": "done"}]])
    agent = Agent(replace(cfg, max_steps=20), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, mode=mode, context_state={"spec": "export"})
    return agent, sess, list(agent.chat(sess.id, "Implement task 1 of spec export: Task"))


def reminders(llm):
    final = llm.calls[-1]["messages"]
    return [c["text"] for m in final for b in m["content"] for c in b.get("toolResult", {}).get("content", [])
            if c.get("text", "").startswith("<spec_reminder")]


def test_a_long_turn_is_reminded_twice_and_the_system_prompt_is_untouched(repo, store, cfg):
    agent, _, events = long_turn(repo, store, cfg, "- [-] 1. Task\n  - _Requirements: 1.1_\n")
    assert [e["task"] for e in events if e["type"] == "spec_reminder"] == ["1", "1"]
    assert len(reminders(agent.llm)) == 2
    assert all(call["system"] == agent.llm.calls[0]["system"] for call in agent.llm.calls)


def test_no_reminder_without_a_task_in_progress(repo, store, cfg):
    agent, _, events = long_turn(repo, store, cfg, "- [ ] 1. Task\n")
    assert not [e for e in events if e["type"] == "spec_reminder"] and not reminders(agent.llm)


def test_no_reminder_outside_spec_mode(repo, store, cfg):
    agent, _, events = long_turn(repo, store, cfg, "- [-] 1. Task\n", mode="build")
    assert not [e for e in events if e["type"] == "spec_reminder"] and not reminders(agent.llm)


def test_a_reminder_isnt_a_turn_and_stays_out_of_the_transcript(repo, store, cfg):
    _, sess, _ = long_turn(repo, store, cfg, "- [-] 1. Task\n  - _Requirements: 1.1_\n")
    assert sum(_is_user_turn(m) for _, m in store.messages(sess.id)) == 1
    assert len(store.turn_starts(sess.id)) == 1
    shown = [e for e in history_events(store, sess.id) if e["type"] in ("tool_result", "user")]
    assert shown and not [e for e in shown if "spec_reminder" in str(e)]


def test_a_turn_that_keeps_pausing_for_approval_is_still_reminded(repo, store, cfg):
    from dataclasses import replace
    spec_with(repo, "- [-] 1. Task\n")
    llm = FakeLLM([[tool_use(f"t{i}", "run_command", command=f"./step{i}")] for i in range(7)] + [[{"text": "done"}]])
    agent = Agent(replace(cfg, max_steps=20), store, llm=llm)
    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, mode="spec", context_state={"spec": "export"})
    events = list(agent.chat(sess.id, "Implement task 1 of spec export: Task"))
    while store.get_session(sess.id).pending:
        events += agent.resume(sess.id, approve=True)
    assert [e["task"] for e in events if e["type"] == "spec_reminder"] == ["1"] and len(reminders(llm)) == 1


def test_the_count_starts_again_with_each_turn(repo, store, cfg):
    agent, sess, _ = long_turn(repo, store, cfg, "- [-] 1. Task\n", steps=5)
    agent.llm.script = [[tool_use("x", "read_file", path="x.py")], [{"text": "done"}]]
    events = list(agent.chat(sess.id, "next"))
    assert not [e for e in events if e["type"] == "spec_reminder"]
