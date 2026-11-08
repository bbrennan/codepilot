# Requirements: a spec task is done when its tests pass

## Introduction

Roadmap 2, item 11. Today `update_task(task, "done")` is the model's word: a task can be ticked with failing tests, or
with none. That is the spec workflow's weakest point. Decided 2026-11-08: the task names the tests that cover its
acceptance criteria, and codepilot runs exactly those before it marks the task done.

Out of scope: choosing tests for the model, coverage measurement, and tests for changes still waiting for review.

## 1. Done means its tests passed

**User story:** As the developer, I want a task marked done only when the tests for it pass, so that a ticked task
means working code, not a claim.

1.1 WHEN codepilot marks a task done THEN it SHALL name the tests that cover the task's acceptance criteria, and the
system SHALL run the workspace's test command with exactly those tests.
1.2 IF those tests fail, or nothing is named, THEN the system SHALL refuse to mark the task done and SHALL tell
codepilot why (the failing output, or what to name).
1.3 IF changes are waiting for review THEN the system SHALL refuse to mark a task done until they are applied, since
the tests would run against the code without them.
1.4 WHERE a task has nothing to test (documentation, say) codepilot MAY mark it done without tests by saying why; the
system SHALL record and show that reason.
1.5 IF the workspace has no test command THEN the system SHALL refuse tests and say how to set one
(`CODEPILOT_TEST_CMD`), leaving the untested route of 1.4.

## 2. Asking first, as for any test run

2.1 Running a task's tests SHALL ask for approval exactly as `run_tests` does: skipped by **auto-run tests** or
`CODEPILOT_AUTO_APPROVE_TESTS`, and never waved through by an "always allow" rule after external content.
2.2 The approval SHALL show the command that will run.

## 3. You can see it

3.1 WHEN a task is marked done THEN `tasks.md` SHALL list its tests under it (`_Tests: …_`), or the reason it has none.
3.2 The spec run card SHALL show the result on the task's row ("✓ 3 tests pass", or "not tested: <reason>").
