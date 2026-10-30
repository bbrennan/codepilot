# Tasks: turn checkpoints

- [x] 1. Find a turn's applied changes
  - Test first in `tests/test_checkpoints.py`: changes before and after a message's `created`; newest first.
  - `Store.applied_since`; `checkpoints.since`.
  - _Requirements: 1.1, 2.1_
- [x] 2. Preview which changes can be undone
  - Tests: a single change; a chain on one file; a created file; a file edited after apply; a blocked newer change
    blocking older ones.
  - `checkpoints.preview` with an injectable reader.
  - _Requirements: 1.5, 3.1, 3.2_
- [x] 3. Restore exactly the confirmed changes
  - Tests: only the given ids are reverted; statuses become `reverted`; a failing writer raises `RestoreError` with a
    partial result.
  - `checkpoints.restore`, built on `tools.revert_proposal`.
  - _Requirements: 1.2, 3.3, 3.4_
- [x] 4. Rewind with restore, and the endpoints
  - Tests in `test_queue_rewind.py` and `test_server.py`: `Agent.rewind(restore=...)` order, events and notice;
    messages kept on `RestoreError`; reverted outcomes appear in the next turn context.
  - The `checkpoint` GET and `restore` POST endpoints, with 409 while busy.
  - _Requirements: 1.2, 1.6, 2.3, 2.4, 3.4_
- [x] 5. Confirmation dialog for Edit and Retry
  - E2E first: retry after the "fix two" turn with auto-apply on shows two changes; confirming restores the files;
    unticking keeps them; a file changed since is shown as left.
  - `static/checkpoints.js` (`checkpointFor`, `confirmRewind`); `editMessage` and `retryFrom` call it; add the script to
    `index.html`; extend CI's `node --check` to `codepilot/static/*.js`.
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.7_
- [x] 6. Undo file changes from here
  - E2E: the ↶ button appears only when there are applied changes; undoing keeps the messages; the proposal cards show
    `reverted`.
  - The extra button in `markTurn`, with a lazy preview on hover.
  - _Requirements: 2.1, 2.2_
- [x] 7. Docs
  - `docs/usage.md` ("Edit or retry", "Changes"): what is and isn't undone.
  - _Requirements: 1.7_
