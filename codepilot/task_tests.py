"""A spec task is done when its tests pass. To mark a task done, the model names the tests that cover its acceptance
criteria, and codepilot runs exactly those (the workspace's test command with those test ids) before it ticks the task;
or the model says why the task has nothing to test, and that reason is recorded. Running them asks first, as run_tests
does, since the model chooses what runs.

Changes waiting for review aren't on disk, so their tests can't run yet: the task is marked done after the review.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass

MAX_TESTS, MAX_ID, MAX_REASON = 50, 300, 200
EXIT = re.compile(r"^exit code (-?\d+)", re.M)


class NotDone(Exception):
    """Why the task can't be marked done yet; the model is told."""


@dataclass
class Done:
    line: str  # recorded under the task in tasks.md
    said: str  # what the model is told
    event: dict  # added to the spec event, for the card


def names(tests) -> list[str]:
    """The test ids as given ([] if none). A string is split on spaces: some models send one."""
    if isinstance(tests, str):
        tests = tests.split()
    return [str(t).strip() for t in tests if str(t).strip()] if isinstance(tests, list) else []


def runs(tool_input: dict) -> bool:
    """Does this update_task call run tests?"""
    return tool_input.get("status") == "done" and bool(names(tool_input.get("tests")))


def asks(tool_input: dict, auto_approve_tests: bool) -> bool:
    """Ask first, as for run_tests (the session's auto-run switch is applied by the tool)."""
    return runs(tool_input) and not auto_approve_tests


def describe(tool_input: dict, test_cmd: str) -> str:
    """The approval's text: the command that will run."""
    tests = " ".join(shlex.quote(t) for t in names(tool_input.get("tests")))
    return f"{test_cmd or '(no test command detected)'} {tests} (to mark task {tool_input.get('task', '')} done)"


def check(pending: list[int], tests, untested: str, test_cmd: str, run: Callable[[list[str]], str]) -> Done:
    """What marking a task done takes: no changes waiting for review, then its tests passing (`run` runs an argv in the
    workspace and returns its output with an "exit code N" line), or a reason it has none. NotDone says what's
    missing."""
    if pending:
        raise NotDone(f"Change{'s' if len(pending) > 1 else ''} {', '.join(f'#{i}' for i in pending)} "
                      f"{'are' if len(pending) > 1 else 'is'} waiting for the user's review: not on disk, so the "
                      "task's tests can't run against them yet. Stop here; once they're applied, mark the task done "
                      "again.")
    ids = names(tests)
    reason = untested.strip() if isinstance(untested, str) else ""
    if not ids:
        if reason and len(reason) <= MAX_REASON:
            return Done(f"_Tests: none ({reason})_", f"not tested: {reason}.", {"untested": reason})
        raise NotDone("To mark a task done, name the tests that cover its acceptance criteria in `tests` (test files "
                      "or test ids the test command takes); codepilot runs them. If the task has nothing to test "
                      f"(documentation, say), give the reason in `untested` instead (up to {MAX_REASON} characters).")
    if option := next((t for t in ids if t.startswith("-")), None):
        raise NotDone(f"{option!r} is an option, not a test. Name test files or test ids.")
    if len(ids) > MAX_TESTS or any(len(t) > MAX_ID for t in ids):
        raise NotDone(f"Name at most {MAX_TESTS} tests, each up to {MAX_ID} characters.")
    if not test_cmd:
        raise NotDone("No test command is known for this workspace, so its tests can't run: the user can set "
                      "CODEPILOT_TEST_CMD. If the task really has nothing to test, mark it done with `untested` and "
                      "why.")
    out = run(shlex.split(test_cmd) + ids)
    code = EXIT.search(out)
    if not code or code.group(1) != "0":
        raise NotDone(f"The task's tests failed, so it's not marked done. Fix what fails and mark it done "
                      f"again.\n{out}")
    n = len(ids)
    return Done(f"_Tests: {', '.join(ids)}_", f"its {n} test{'s' if n != 1 else ''} pass.\n{out}", {"tests": n})
