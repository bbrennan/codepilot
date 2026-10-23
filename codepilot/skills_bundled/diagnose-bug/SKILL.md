---
name: diagnose-bug
description: Disciplined diagnosis loop for bugs, failing tests, crashes, wrong output, flaky behaviour and performance regressions. Use for "why does X fail", "debug this", stack traces, or any bug report.
---
# Diagnose a bug

The whole game is a fast, reliable feedback loop. Do not guess at fixes before you have one.

## 1. Build a feedback loop (most important)
Get ONE command that goes red on this exact bug, then make it fast and deterministic. In order of preference:
1. An existing test that fails: `run_tests` with a path or `-k name`.
2. A new failing test (propose it, or write it to scratch first and run it directly).
3. A repro script: `write_scratch` (e.g. `repro.py` that imports the workspace code and asserts the expected
   behaviour), then `run_command "python3 <scratch path>"`.
4. A replay of a recorded input: a request from logs/traces, a saved payload, a CLI invocation.
5. `git bisect run <repro command>` (via run_command) when it used to work and you know a good commit.
6. A differential check (old vs new output, or ours vs a reference).

For flaky bugs, loop the repro (e.g. 50 runs) until you can make it fail reliably. If no loop is possible,
stop and tell the user what you need (an input, an environment, access).
Never print secrets in repros or logs; write `<REDACTED>`.

## 2. Reproduce and minimise
Confirm the failure matches the user's symptom (same error, same wrong value). Shrink the input until every
remaining piece is needed. Note the exact expected vs actual.

## 3. Hypothesise
Write 3-5 ranked, falsifiable hypotheses: "If X is the cause, then changing Y makes the failure disappear."
Show them to the user (briefly) before testing. Use `explore` for wide searches (all callers, all writers of
a value) so the main thread stays focused.

## 4. Test hypotheses one at a time
Change one variable per run. Prefer instrumenting inside the scratch harness (asserts, prints of
intermediate values) over editing workspace code. If workspace code must be instrumented, propose clearly
tagged lines (`# [DEBUG-xxxx]`) and remove them before finishing. For performance, measure a baseline first
and compare numbers, not impressions.

## 5. Fix and lock it in
- State the root cause in 1-2 sentences with `path:line`. Distinguish it from the symptom.
- Propose the smallest fix at the cause, in the surrounding style (`propose_edit`).
- Propose a regression test at the right seam (it must fail without the fix). If there is no sensible seam,
  say so; that is a finding in itself.
- After the user applies: re-run the regression test, the original repro, then the wider suite.

## 6. Clean up and report
Remove debug lines and scratch harnesses from the workspace. Report: root cause, evidence, the fix, what you
ran and its result, and anything still unverified.
