"""A spec task is done when its tests pass. To mark a task done, the model names the tests that cover its acceptance
criteria, and codepilot runs exactly those (the workspace's test command with those test ids) before it ticks the task;
or the model says why the task has nothing to test, and that reason is recorded. Running them asks first, as run_tests
does, since the model chooses what runs.

Changes waiting for review aren't on disk, so their tests can't run yet: the task is marked done after the review.
"""

from __future__ import annotations

import json
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
    """The test ids as given ([] if none). A string is read as the tool reads it (tools._coerce): a JSON array, else
    one test per line. So the approval shows exactly what runs."""
    if isinstance(tests, str):
        try:
            tests = json.loads(tests)
        except json.JSONDecodeError:
            tests = tests.splitlines()
    return [str(t).strip() for t in tests if str(t).strip()] if isinstance(tests, list) else []


def selector(test_cmd: str) -> list[str] | None:
    """The test command, ready to be given test names; None if it can't take them (make takes targets)."""
    argv = shlex.split(test_cmd)
    if not argv or argv[0] == "make":
        return None
    if argv[:2] == ["go", "test"]:  # its default selects every package, which would run as well
        return [a for a in argv if a != "./..."]
    if argv[0] in ("npm", "pnpm") and argv[1:2] == ["test"] and "--" not in argv:  # they pass on names after --
        return [*argv, "--"]
    return argv


def runs(tool_input: dict) -> bool:
    """Does this update_task call run tests?"""
    return tool_input.get("status") == "done" and bool(names(tool_input.get("tests")))


def asks(tool_input: dict, auto_approve_tests: bool) -> bool:
    """Ask first, as for run_tests (the session's auto-run switch is applied by the tool)."""
    return runs(tool_input) and not auto_approve_tests


def describe(tool_input: dict, test_cmd: str) -> str:
    """The approval's text: the command that will run."""
    argv = selector(test_cmd) if test_cmd else None
    shown = shlex.join(argv + names(tool_input.get("tests"))) if argv else (
        f"{test_cmd} (it can't run single tests)" if test_cmd else "(no test command detected)")
    return f"{shown} (to mark task {tool_input.get('task', '')} done)"


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
    reason = " ".join(untested.split()) if isinstance(untested, str) else ""  # one line: it goes in tasks.md
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
    if broken := next((t for t in ids if "\n" in t or "\r" in t), None):  # it would fake lines of the output
        raise NotDone(f"{broken!r} has a line break: name one test per item.")
    if not test_cmd:
        raise NotDone("No test command is known for this workspace, so its tests can't run: the user can set "
                      "CODEPILOT_TEST_CMD. If the task really has nothing to test, mark it done with `untested` and "
                      "why.")
    argv = selector(test_cmd)
    if argv is None:
        raise NotDone(f"The test command ({test_cmd}) can't run single tests, so this task's tests can't run on their "
                      "own: the user can set CODEPILOT_TEST_CMD to one that takes test names (pytest, say).")
    out = run(argv + ids)
    code = EXIT.search(out)
    if not code or code.group(1) != "0":
        raise NotDone(f"The task's tests failed, so it's not marked done. Fix what fails and mark it done "
                      f"again.\n{out}")
    n = len(ids)
    return Done(f"_Tests: {', '.join(ids)}_", f"its {n} test{'s' if n != 1 else ''} pass.\n{out}", {"tests": n})
