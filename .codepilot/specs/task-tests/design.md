# Design

## Where it lives

- `codepilot/task_tests.py` (new): what "done" requires. `check(ctx, spec, task_id, tests, untested)` validates the
  call, refuses while changes are pending, runs `<test command> <tests…>` in the workspace and returns the line to
  record, or raises `ToolError` with the reason (1.1–1.5). `asks(input, cfg)` and `describe(input, root, cfg)` serve
  the approval (2.1, 2.2).
- `specs.py`: `set_task_tests(path, task_id, text)` writes or replaces the task's `_Tests: …_` line (3.1).
- `tools.py` (wiring): `update_task` gains `tests` (list of test ids) and `untested` (a reason). For status `done` it
  calls `task_tests.check` before ticking. The tool's per-call approval is `task_tests.asks`, and it is auto-approvable
  like `run_tests`; `Tool.requires_approval` lets auto-run skip a per-call approval when the tool is auto-approvable
  (no current per-call tool is, so nothing else changes).
- `approval_policy.py`: a done with tests is guarded like `run_tests` with arguments: the model chooses what runs (2.1).
- `agent.py` (`describe`): the approval shows `task_tests.describe` (2.2).
- `spec_profiles.py`: the implement instructions say to name the tests, or say why there are none.
- `static/specrun.js`: the task's note comes first from its done step: "✓ n tests pass" or "not tested: why" (3.2).

## Decisions

- Tests are run, not looked up: a fresh run at the moment of "done" is the only result that can't be stale.
- Test ids go to the test command as separate arguments (`pytest tests/x.py::test_y`, `go test ./pkg`), so it works
  with any runner that takes names. An id that starts with `-` is refused: it would be an option, not a test.
- Pending changes are refused rather than verified on a copy: after review, codepilot carries on and marks the task
  done then, so the run pauses where you decide anyway.

## Tests

Unit: done without tests or reason is refused; passing tests tick it and write `_Tests_`; failing tests don't, and
return the output; pending changes and a missing test command are refused; the untested reason is recorded; approval
asks for a done with tests, not with auto-run, and not for other statuses. E2E: the spec run card shows the result.
