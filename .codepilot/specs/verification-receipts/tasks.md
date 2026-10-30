# Tasks: verification receipts

- [x] 1. Clone the workspace and apply the pending changes to the copy
  - Test first: `clone_tree` on a temp folder; applying proposals in order; a conflict gives `error`; the workspace is
    unchanged byte for byte; the copy is removed in `finally`.
  - `verification.clone_tree`, `fingerprint`, and the apply step of `verify` with an injected copier.
  - `relocate_envs`, with a test on a fake virtualenv (shebang script, editable finder, `.pth`, a binary file left
    alone) and the leftover scan; plus one real check that a copied `python -m venv` runs the copy's module.
  - _Requirements: 1.3, 1.4, 1.6, 1.8, 4.2_
- [x] 2. Run tests and analysers, with a baseline on failure
  - Tests with a fake runner: pass; newly failing vs already failing; the baseline runs only on failure;
    `newly_failing` parsing for pytest, Jest and go test, and for analyser lines; timeout; cancel.
  - The rest of `verification.verify`; `run_argv`, which reuses the environment handling of `tools._run_command`.
  - _Requirements: 1.5, 2.6, 4.1_
- [x] 3. Store receipts
  - Tests: an additive migration on an old database; `add_receipt` and `latest_receipt`; the `told` flag.
  - The `receipts` table and the `Store` methods.
  - _Requirements: 2.2, 3.5_
- [x] 4. The `verify_changes` tool and the automatic run at turn end
  - Tests in `test_agent.py`: needs approval unless auto-run is on; automatic only when due; no repeat for a matching
    fingerprint; a `verification` event before `done`; the receipt in the next turn context exactly once.
  - Register the tool in `tools.py`; `Agent.verify`; `verification_due`; `_turn_context`; `CODEPILOT_VERIFY` and
    `CODEPILOT_VERIFY_TIMEOUT` in `config.py`.
  - _Requirements: 1.1, 3.1, 3.2, 3.3, 3.5, 4.3_
- [x] 5. Endpoint, cancel, and clean-up at start
  - Tests in `test_server.py`: `/verify` streams a receipt, returns 409 while busy, and Cancel works; the session JSON
    has `receipt`; leftover copies are removed at start.
  - _Requirements: 1.7, 4.2_
- [x] 6. Receipt in the review bar and the Review tab
  - E2E first: not verified → Verify → ✓; stale after a reject; "verifying…" held with `page.route`; the Review tab
    header and per-file findings.
  - `static/verify.js`; the hooks in `renderReviewBar` and `renderReviewTab`.
  - _Requirements: 1.2, 1.7, 2.1, 2.2, 2.3_
- [x] 7. Chat card and Ask codepilot to fix
  - E2E: the card expands to the runs; Details scrolls to it; the fix button sends the failures.
  - `render()` handles `case "verification"`.
  - _Requirements: 2.4, 2.5_
- [ ] 8. Instructions and docs
  - The request to verify lives in the tool description, not the mode text (3.4). Run a benchmark before and after with
    `codepilot bench compare`, as CONTRIBUTING asks for tool changes.
  - `docs/usage.md` (Changes), `docs/configuration.md`, `docs/security.md` (tests run on a copy, as you).
  - _Requirements: 3.4, 4.3_
