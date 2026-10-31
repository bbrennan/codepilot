# Tasks: taint-aware approvals

- [x] 1. Detect destructive commands
  - Test first: the table rows, chained and piped commands, false-positive guards, quoting failures.
  - `approval_policy.destructive`, with the pattern table as data.
  - _Requirements: 3.1, 3.3_
- [x] 2. The advice hook, wired into the loop
  - Tests: merging advice; `force_ask` overrides rules and the tool default; `offer_rule=False` removes `allow` from the
    approval view and from `resume(remember=True)`; destructive commands never match a saved rule.
  - `Advice`, `View`, `advise`, `destructive_advisor`; the `_loop_steps`, `approval_view`, `resume` and `rule_matches`
    changes. Advice is computed when needed, not stored.
  - _Requirements: 3.2, 4.1_
- [x] 3. Record taint
  - Tests: `taint_source` for each tool; recorded from the main loop and from explore; de-duplicated and capped; the
    `taint` event fires once; it persists across reopen and compaction; `handoff` starts clean.
  - `taint_source`; recording in `_exec` and `_explore`.
  - _Requirements: 1.1, 1.2, 1.3_
- [x] 4. Stricter approvals while tainted
  - Tests in `test_approvals.py`: rules paused; `web_fetch`, `web_search` and `library_docs` ask; explore refuses; tests
    still auto-run; clearing via PATCH restores the rules.
  - `taint_advisor`; the PATCH `taint` field; the session JSON.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7_
- [x] 5. Tell the model once
  - Test: the turn context note appears exactly once per session.
  - _Requirements: 1.5_
- [x] 6. UI: chip, warnings, paused rules
  - E2E first: a fetch and then a command shows the chip and the reason, with no "always allow"; Clear restores it; the
    `rm -rf` warning is red; Memory shows the rules as paused.
  - `static/policy.js`; `#taintChip` in `index.html`; hooks in `renderReviewBar`, `renderMemory` and `render()`.
  - _Requirements: 1.4, 2.5, 3.1_
- [x] 7. Docs
  - `docs/security.md` (Prompt injection: what taint does and doesn't do), `docs/usage.md` (Approvals).
  - _Requirements: 1.4, 2.1_
