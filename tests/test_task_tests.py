"""A spec task is done when its tests pass: codepilot runs the tests the task names before it ticks it, asking first
as for any test run. (Spec task-tests.)"""

import shutil
from dataclasses import replace

import pytest
from fakes import FakeLLM, tool_use

from codepilot import approval_policy as policy
from codepilot import specs
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
