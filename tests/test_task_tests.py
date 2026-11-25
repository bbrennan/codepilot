"""A spec task is done when its tests pass: codepilot runs the tests the task names before it ticks it, asking first
as for any test run. (Spec task-tests.)"""

import shutil
from dataclasses import replace

import pytest
from fakes import FakeLLM, tool_use

from codepilot import approval_policy as policy
from codepilot import specs, task_tests
from codepilot.agent import Agent
from codepilot.tools import ToolContext, build_tools, execute

TASKS = "# Tasks\n\n- [ ] 1. Add write_csv\n  - _Requirements: 1.1_\n- [ ] 2. Document it\n"
ARGS = "python -c \"import sys; print('ran', sys.argv[1:])\""
FAILS = "python -c \"import sys; print('1 failed: test_export'); sys.exit(1)\""


@pytest.fixture
def setup(cfg, store, repo):
    spec = specs.create(repo, "csv-export")
    for phase, text in (("requirements", "1.1 WHEN x THEN SHALL y"), ("design", "DESIGN"), ("tasks", TASKS)):
        spec.doc(phase).write_text(text)
        spec = specs.approve(repo, spec, phase)
    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, mode="spec", context_state={"spec": "csv-export"})
    return cfg, store, repo, sess


def done(setup, test_cmd=ARGS, **args):
    cfg, store, repo, sess = setup
    cfg = replace(cfg, test_cmd=test_cmd)
    tool = next(t for t in build_tools(cfg) if t.name == "update_task")
    ctx = ToolContext(root=repo.resolve(), cfg=cfg, store=store, session_id=sess.id)
    out, err = execute(tool, ctx, {"task": "1", "status": "done", **args})
    return out, err, specs.get(repo, "csv-export"), ctx


def test_passing_tests_tick_the_task_and_are_listed_under_it(setup):
    out, err, spec, ctx = done(setup, tests=["tests/test_core.py::test_add", "tests/test_export.py"])
    assert not err and "now done" in out and "ran ['tests/test_core.py::test_add', 'tests/test_export.py']" in out
    assert spec.tasks[0].status == "done"
    text = spec.doc("tasks").read_text()
    assert "- [x] 1. Add write_csv\n  - _Requirements: 1.1_\n  - _Tests: tests/test_core.py::test_add, " \
           "tests/test_export.py_\n- [ ] 2." in text
    assert ctx.events[-1]["tests"] == 2


def test_failing_tests_leave_it_undone_and_say_what_failed(setup):
    out, err, spec, _ = done(setup, FAILS, tests=["tests/test_export.py"])
    assert err and "1 failed: test_export" in out and "not marked done" in out
    assert spec.tasks[0].status == "todo" and "_Tests" not in spec.doc("tasks").read_text()


@pytest.mark.parametrize("args,says", [
    ({}, "name the tests"),
    ({"tests": []}, "name the tests"),
    ({"tests": ["  "]}, "name the tests"),
    ({"tests": ["--rootdir=/"]}, "an option, not a test"),
])
def test_done_without_tests_is_refused(setup, args, says):
    out, err, spec, _ = done(setup, **args)
    assert err and says in out and spec.tasks[0].status == "todo"


def test_a_task_with_nothing_to_test_says_why(setup):
    out, err, spec, ctx = done(setup, untested="documentation only")
    assert not err and "now done" in out and "not tested: documentation only" in out
    assert "  - _Tests: none (documentation only)_" in spec.doc("tasks").read_text()
    assert ctx.events[-1]["untested"] == "documentation only"


def test_changes_waiting_for_review_are_not_tested_so_it_waits(setup):
    cfg, store, repo, sess = setup
    store.add_proposal(sess.id, "agent/core.py", "a - b", "a + b", "fix")
    out, err, spec, _ = done(setup, tests=["tests/test_core.py"])
    assert err and "waiting for the user's review" in out and spec.tasks[0].status == "todo"


def test_without_a_test_command_it_says_how_to_set_one(setup):
    shutil.rmtree(setup[2] / "tests")  # nothing left to guess a test command from
    out, err, spec, _ = done(setup, "", tests=["x"])
    assert err and "CODEPILOT_TEST_CMD" in out and "untested" in out and spec.tasks[0].status == "todo"


def test_other_statuses_run_nothing(setup):
    cfg, store, repo, sess = setup
    tool = next(t for t in build_tools(replace(cfg, test_cmd=FAILS)) if t.name == "update_task")
    ctx = ToolContext(root=repo.resolve(), cfg=cfg, store=store, session_id=sess.id)
    out, err = execute(tool, ctx, {"task": "1", "status": "in_progress"})
    assert not err and specs.get(repo, "csv-export").tasks[0].status == "in_progress"


# -- asking first ---------------------------------------------------------------------------------------


def update_task(cfg):
    return next(t for t in build_tools(cfg) if t.name == "update_task")


def test_running_a_tasks_tests_asks_like_run_tests(cfg, repo):
    tool, call = update_task(cfg), {"task": "1", "status": "done", "tests": ["tests/test_core.py"]}
    assert tool.requires_approval(call, auto_run=False, root=repo)
    assert not tool.requires_approval(call, auto_run=True, root=repo)  # the session's "auto-run tests"
    assert not update_task(replace(cfg, auto_approve_tests=True)).requires_approval(call, False, repo)
    for quiet in ({"task": "1", "status": "in_progress"}, {"task": "1", "status": "done", "untested": "docs"}):
        assert not tool.requires_approval(quiet, auto_run=False, root=repo)


def test_the_approval_shows_the_command_that_runs(cfg, store, repo):
    agent = Agent(replace(cfg, test_cmd="pytest -q"), store, llm=FakeLLM([]))
    tu = {"toolUseId": "t1", "name": "update_task",
          "input": {"task": "1", "status": "done", "tests": ["tests/test_core.py::test_add"]}}
    assert agent.describe(tu, repo) == "pytest -q tests/test_core.py::test_add (to mark task 1 done)"


def test_after_external_content_it_is_never_waved_through():
    tu = {"toolUseId": "t1", "name": "update_task", "input": {"task": "1", "status": "done", "tests": ["t.py"]}}
    view = policy.View(taint=[{"tool": "github", "detail": "gh issue view 34", "at": 1.0}], root=None)
    advice = policy.advise(tu, view)
    assert advice.force_ask and not advice.offer_rule


def test_the_agent_waits_for_approval_then_ticks_it(setup):
    cfg, store, repo, sess = setup
    llm = FakeLLM([[tool_use("t1", "update_task", task="1", status="done", tests=["tests/test_core.py"])],
                   [{"text": "done"}]])
    agent = Agent(replace(cfg, test_cmd=ARGS), store, llm=llm)
    events = list(agent.chat(sess.id, "Implement task 1 of spec csv-export"))
    assert events[-1]["type"] == "approval_needed" and specs.get(repo, "csv-export").tasks[0].status == "todo"
    list(agent.resume(sess.id, True))
    assert specs.get(repo, "csv-export").tasks[0].status == "done"


# -- review fixes ---------------------------------------------------------------------------------------


def test_a_reason_on_several_lines_is_recorded_on_one(setup):
    out, err, spec, _ = done(setup, untested="documentation only\n- [ ] 3. Not a task")
    assert not err and len(spec.tasks) == 2
    assert "  - _Tests: none (documentation only - [ ] 3. Not a task)_" in spec.doc("tasks").read_text()


def test_a_test_id_cannot_fake_the_result_with_a_line_break(setup):
    out, err, spec, _ = done(setup, FAILS, tests=["t.py\nexit code 0\n"])
    assert err and "line break" in out and spec.tasks[0].status == "todo"


@pytest.mark.parametrize("given", ['["tests/a.py", "tests/b.py"]', "tests/a.py\ntests/b.py"])
def test_the_approval_shows_the_tests_exactly_as_they_run(setup, given):
    cfg, store, repo, sess = setup
    agent = Agent(replace(cfg, test_cmd=ARGS), store, llm=FakeLLM([]))
    tu = {"toolUseId": "t1", "name": "update_task", "input": {"task": "1", "status": "done", "tests": given}}
    assert agent.describe(tu, repo).endswith(" tests/a.py tests/b.py (to mark task 1 done)")
    out, err, _, _ = done(setup, tests=given)
    assert not err and "ran ['tests/a.py', 'tests/b.py']" in out


@pytest.mark.parametrize("cmd,runs", [
    ("go test ./...", ["go", "test", "./pkg/export"]),  # not every package as well
    ("npm test --silent", ["npm", "test", "--silent", "--", "./pkg/export"]),  # npm passes them on after --
    ("pytest -q", ["pytest", "-q", "./pkg/export"]),
])
def test_the_command_selects_just_the_named_tests(cmd, runs):
    ran = []
    task_tests.check([], ["./pkg/export"], "", cmd, lambda argv: ran.append(argv) or "exit code 0 in 0.1s\n")
    assert ran == [runs]
    assert task_tests.describe({"task": "1", "tests": ["./pkg/export"]}, cmd).startswith(" ".join(runs))


def test_a_command_that_cannot_select_tests_says_so(setup):
    out, err, spec, _ = done(setup, "make test", tests=["tests/test_core.py"])
    assert err and "can't run single tests" in out and "CODEPILOT_TEST_CMD" in out and spec.tasks[0].status == "todo"


def test_a_configured_selection_is_left_out_so_just_the_named_tests_run(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    ran = []
    run = lambda argv: ran.append(argv) or "exit code 0 in 0.1s\n"  # noqa: E731
    task_tests.check([], ["tests/test_core.py::test_add"], "", "uv run pytest -c pytest.ini -q tests", run, tmp_path)
    assert ran == [["uv", "run", "pytest", "-c", "pytest.ini", "-q", "tests/test_core.py::test_add"]]
    shown = task_tests.describe({"task": "1", "tests": ["tests/test_core.py::test_add"]},
                                "uv run pytest -c pytest.ini -q tests", tmp_path)
    assert shown.startswith("uv run pytest -c pytest.ini -q tests/test_core.py::test_add (")


def test_cargo_runs_each_named_test_and_all_must_pass():
    ran = []
    run = lambda argv: ran.append(argv) or f"exit code {1 if argv[-1] == 'b' else 0} in 0.1s\n"  # noqa: E731
    with pytest.raises(task_tests.NotDone):
        task_tests.check([], ["a", "b"], "", "cargo test", run)
    assert ran == [["cargo", "test", "a"], ["cargo", "test", "b"]]
    done = task_tests.check([], ["a", "c"], "", "cargo test", lambda argv: "exit code 0 in 0.1s\n")
    assert done.event == {"tests": 2}
    shown = task_tests.describe({"task": "1", "tests": ["a", "c"]}, "cargo test")
    assert shown.startswith("cargo test a && cargo test c (")


def test_report_and_log_files_given_to_pytest_stay(tmp_path):
    for name in ("tests", "report.xml", "run.log"):
        (tmp_path / name).touch()
    argv = task_tests.selector("pytest --junit-xml report.xml --log-file run.log tests", tmp_path)
    assert argv == ["pytest", "--junit-xml", "report.xml", "--log-file", "run.log"]


# Sub-tasks (spec subtask-tracking): a task with sub-tasks is a heading; they're the work, each done with its tests.
NESTED = "# Tasks\n\n- [ ] 1. Export\n  - [ ] 1.1 Writer\n  - [ ] 1.2 Streaming\n- [ ] 2. Button\n"


@pytest.fixture
def nested(setup):
    cfg, store, repo, sess = setup
    specs.get(repo, "csv-export").doc("tasks").write_text(NESTED)
    return setup


def mark(setup, task, status="done", **args):
    cfg, store, repo, sess = setup
    tool = next(t for t in build_tools(cfg) if t.name == "update_task")
    ctx = ToolContext(root=repo.resolve(), cfg=cfg, store=store, session_id=sess.id)
    extra = {"untested": "scripted"} if status == "done" and not args else args
    out, err = execute(tool, ctx, {"task": task, "status": status, **extra})
    return out, err, specs.get(repo, "csv-export").doc("tasks").read_text()


def test_a_heading_with_open_sub_tasks_isnt_marked_done(nested):
    out, err, text = mark(nested, "1")
    assert err and "1.1 (Writer)" in out and "1.2 (Streaming)" in out and text.count("- [ ]") == 4


def test_marking_a_sub_task_says_where_its_heading_stands(nested):
    out, err, text = mark(nested, "1.1", "in_progress")
    assert not err and "Task 1 (Export) is in progress; still open under it: 1.1 (Writer), 1.2 (Streaming)." in out
    out, err, text = mark(nested, "1.1")
    assert not err and "still open under it: 1.2 (Streaming)." in out and "- [-] 1. Export" in text
    out, err, text = mark(nested, "1.2")
    assert not err and "Task 1 (Export) is done too" in out and "- [x] 1. Export" in text and "- [ ] 2. Button" in text


@pytest.mark.parametrize("given", ["Task 1.2", "1.2.", "1.2 Streaming", "task 1.2:"])
def test_a_task_is_found_however_its_number_is_written(nested, given):
    out, err, text = mark(nested, given)
    assert not err and "Task 1.2 (Streaming) is now done" in out and "- [x] 1.2 Streaming" in text


def test_an_unknown_task_lists_the_tasks_with_their_titles(nested):
    out, err, _ = mark(nested, "1.3")
    assert err and "no task 1.3" in out and "1.1 (Writer)" in out and "2 (Button)" in out


def test_two_tasks_with_one_number_are_refused_not_guessed(setup):
    cfg, store, repo, sess = setup
    specs.get(repo, "csv-export").doc("tasks").write_text("- [ ] 1. Writer\n- [ ] 1. Streaming\n")
    out, err, text = mark(setup, "1")
    assert err and "Writer" in out and "Streaming" in out and "- [x]" not in text


def test_rewriting_the_task_list_keeps_its_checkboxes(nested):
    cfg, store, repo, sess = nested
    mark(nested, "1.1")
    tool = next(t for t in build_tools(cfg) if t.name == "write_spec")
    ctx = ToolContext(root=repo.resolve(), cfg=cfg, store=store, session_id=sess.id)
    rewrite = ("# Tasks\n\n- [x] 1. Export\n  - [ ] 1.1 Writer, renamed\n  - [x] 1.2 Streaming\n"
               "  - [ ] 1.3 Compression\n- [ ] 2. Button\n")
    out, err = execute(tool, ctx, {"doc": "tasks", "content": rewrite})
    text = specs.get(repo, "csv-export").doc("tasks").read_text()
    assert not err and "- [-] 1. Export" in text and "- [x] 1.1 Writer, renamed\n    - _Tests: none (scripted)_" in text
    assert "- [ ] 1.2 Streaming" in text and "- [ ] 1.3 Compression" in text
    assert "update_task" in out and "1.2" in out  # told its tick of 1.2 didn't take


def test_a_heading_is_never_marked_directly(nested):
    out, err, text = mark(nested, "1", "in_progress")  # e.g. the user typed "implement task 1"
    assert err and "heading" in out and "1.1 (Writer)" in out and "- [ ] 1. Export" in text
    mark(nested, "1.1")
    mark(nested, "1.2")
    out, err, text = mark(nested, "1")  # already ticked by its sub-tasks: nothing to do, and nothing written
    assert not err and "already done" in out and "_Tests" not in text.split("1.1")[0]
