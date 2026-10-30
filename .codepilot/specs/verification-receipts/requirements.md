# Requirements: verification receipts

## Introduction

Proposed edits aren't on disk until I apply them. So when CodePilot runs tests during a turn, it tests the old code,
and nothing tests a change before I approve it. This spec runs the workspace's tests and analysers on a disposable
copy of the workspace with the pending changes applied. The result is a **receipt**: what ran, what passed, and what
newly fails. It shows where I make the decision, in the review bar and the Review tab.

Evidence (research report): developers trust AI output mainly when it is easy to verify (Stack Overflow 2026). About
half of agent patches that pass tests still wouldn't be merged (METR 2026). Security issues don't go away with newer
models (Veracode). So a receipt informs my review; it doesn't replace it.

Out of scope: blocking Apply on a failing receipt (I decide), a container sandbox, and verifying changes that are
already applied (the existing "Continuing after your review" flow covers those).

## 1. Verify pending changes before review

**User story:** As the developer, I want my pending changes tested before I apply them, so that I review changes that
are known to pass, not hoped to.

1.1 WHEN a turn ends with pending changes that have no current receipt AND **auto-run tests** is on THEN the system SHALL
verify them before the turn finishes.
1.2 WHEN changes are pending AND auto-run tests is off THEN the review bar SHALL show "not verified" with a **Verify**
button, and SHALL run nothing until I press it.
1.3 WHEN verifying THEN the system SHALL make a temporary copy of the workspace, apply every pending change of the session
to it in order, run the workspace's test command and the analysers on the changed files there, and delete the copy
afterwards.
1.4 The system SHALL NOT modify the workspace, its `.git` folder or any pending change while verifying.
1.5 IF tests or an analyser fail on the copy THEN the system SHALL also run them on the copy without the changes, and SHALL
label each failure "newly failing" or "already failing".
1.6 IF pending changes can't be combined (one no longer applies after another) THEN the receipt SHALL say which, and SHALL
verify nothing.
1.7 WHILE verifying THEN the review bar SHALL show progress and a **Cancel** button, and the session SHALL count as busy.
1.8 The copy SHALL run its own code, not the workspace's. Virtualenvs copied with it SHALL be re-pointed at the copy, and
IF any reference to the workspace path remains in them THEN the receipt SHALL say "isolation unverified" and SHALL NOT
show as a plain pass.

## 2. Receipts where I decide

**User story:** As the developer, I want the receipt next to Apply, so that I don't have to go looking for test output.

2.1 WHEN a receipt exists for the current pending changes THEN the review bar SHALL show one line: a pass mark with
"tests pass · ruff clean · 4.1s", or a fail mark with "2 tests newly failing", with a **Details** link.
2.2 WHEN the pending set changes (a change is added, applied, rejected, superseded or outdated) THEN the receipt SHALL
become "stale" and offer **Re-verify**. A stale receipt SHALL never be shown as a pass.
2.3 The Review tab SHALL show the receipt in its list header and, for each file, the analyser findings on that file above
its diff.
2.4 Each verification SHALL appear in the chat as one compact, expandable card with the commands, exit codes, the
newly-failing tests and the output tail.
2.5 WHEN a receipt has newly-failing results THEN it SHALL offer **Ask codepilot to fix**, which sends the failures as a
message. The system SHALL NOT start a fix on its own.
2.6 IF the workspace has no test command and no analysers THEN the receipt SHALL say "nothing to run" rather than pass.

## 3. The agent can verify its own proposals

**User story:** As the developer, I want CodePilot to test its proposals before handing them to me, so that it fixes its
own failures first.

3.1 The agent SHALL have a `verify_changes` tool that does what 1.3 and 1.5 describe and returns the receipt as text.
3.2 `verify_changes` SHALL need approval like `run_tests`, which the auto-run tests switch skips.
3.3 WHEN the agent produced a receipt for exactly the current pending set during the turn THEN 1.1 SHALL NOT run again.
3.4 The agent SHALL be asked to call `verify_changes` before ending a turn that leaves changes pending, in the tool's own
description, so every mode that can propose changes sees it, and the request disappears when `CODEPILOT_VERIFY=0`.
3.5 On my next message the assistant SHALL be told the latest receipt for the pending changes if it hasn't seen it.

## 4. Limits

4.1 A verification SHALL stop after `CODEPILOT_VERIFY_TIMEOUT` seconds (default 600) and report "timed out".
4.2 The copy SHALL live under `~/.codepilot/verify/<session>/` and SHALL be removed even when verification fails or is
cancelled. Leftovers from a crash SHALL be removed at server start.
4.3 `CODEPILOT_VERIFY=0` SHALL turn the feature off (no automatic runs, no tool, no review-bar line).
