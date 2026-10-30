# Design: turn checkpoints

## Overview

Every applied proposal already stores `before_text` and `after_text` (`store.record_applied`). Each proposal and
each message also has a `created` timestamp. `Store.discard_pending_since` already uses those timestamps to decide
which proposals belong to rewound turns. A checkpoint is therefore not a snapshot: it is the list of applied proposals
created at or after the turn's first message. Restoring means reverting that list in the reverse of the order the
changes were *applied* (not their numbers: changes are reviewed in any order), using the existing guarded
`tools.revert_proposal`. The only new storage is an `applied_at` time on proposals. (Requirements 1, 2)

## Architecture

```
app.js (Edit / Retry / ↶)  ──GET  /api/sessions/{sid}/checkpoint?mid=   ──► checkpoints.preview()
      static/checkpoints.js ──POST /api/sessions/{sid}/restore {ids}      ──► checkpoints.restore()
                            ──POST /api/sessions/{sid}/rewind {mid, message, restore: ids}
                                                                          ──► Agent.rewind() → checkpoints.restore()
```

### New: `codepilot/checkpoints.py`

Its one reason to change is deciding which applied changes belong to a turn, and how to undo them.

```python
@dataclass
class Item:
    proposal: Proposal
    ok: bool            # can be reverted now
    reason: str = ""    # why not: "changed since it was applied", "a newer change to this file can't be undone"

def since(store: Store, sid: str, mid: int) -> list[Proposal]:
    """Applied proposals created at or after message `mid` of this session, most recently applied first.
    [] if the session has no such message."""

def preview(root: Path, proposals: list[Proposal], read=_read, hold=frozenset()) -> list[Item]:
    """Simulates the reverts per file, most recently applied first, without writing (1.5, 3.2). `hold`: ids to
    leave alone whatever their state, because the user saw them listed as left."""

def restore(root: Path, store: Store, sid: str, ids: list[int], revert=revert_proposal, keep=()
            ) -> tuple[list[Proposal], list[Item]]:
    """Reverts the given ids of this session (only those: 3.3; others are ignored) that preview() still marks ok.
    `keep`: ids the dialog listed as left; they're reported in `left` (so the notice names them, 1.6), never undone.
    Returns (reverted, left). Raises RestoreError(reverted, left, cause) when a write fails partway (3.4)."""

def summary(reverted, left) -> str        # "Undid 2 file changes (a.py, b.py); left 1 as is: …" (1.6)
def failure(exc: RestoreError) -> str     # "Undid 1 of 2 file changes, then couldn't undo a.py: …" (3.4)
```

How `preview` works for each file:
1. Resolve the path, following symlinks. A path that lands outside the repository is left ("outside the repository")
   and never read, which is the same boundary `revert_proposal` enforces. Otherwise read the current content once:
   a missing file is `None`, and a read error leaves that file ("can't be read: …") without failing the others.
2. Walk that file's changes most recently applied first, tracking the expected content. Each change is `ok` only if the expected
   content equals its `after_text`. When it is ok, the expected content becomes its `before_text` (or `None` if the
   change created the file).
3. Once one change on a file is not ok, every older change on that file is also not ok (3.2).

`restore` calls `preview` again just before writing, so the result reflects the disk as it is when you confirm. It
then calls `tools.revert_proposal` for each ok change and `store.set_proposal_status(id, "reverted")`. The
`reported = 0` that `set_proposal_status` already sets is what makes the next `<turn_context>` say "Proposal #N
(...) was reverted by the user" (2.3). No new code is needed for that.

### Changes to existing modules (wiring only)

- **`store.py`:**
  - Add `applied_since(sid, since) -> list[Proposal]`, one query (`status = 'applied' AND created >= ? ORDER BY
    COALESCE(applied_at, 0) DESC, id DESC`). It sits next to `discard_pending_since` and follows the same timestamp
    rule.
  - `record_applied` stamps `applied_at`, an additive column. Rows applied before the migration have none, so they
    sort as oldest, in number order.
  - `message_created(mid, sid=None)` can be limited to a session, so a message id from another session selects
    nothing.
- **`agent.py`:** `Agent.rewind(session_id, mid, text, tier, restore: list[int] | None = None, keep=None)`.
  - When `restore` is set, it calls `checkpoints.restore` first.
  - For each reverted change it yields a `proposal` event with `proposal_view(p, "")`. The browser keeps the diff it
    already has.
  - It then yields `notice` "Restored N files; left M that changed since: …" (1.6).
  - On `RestoreError` it yields `error` and returns without deleting messages (3.4).
- **`server.py`:**
  - `GET /api/sessions/{sid}/checkpoint?mid=` returns `{"changes": [{"id", "path", "ok", "reason"}]}`. It runs in a
    worker thread.
  - `POST /api/sessions/{sid}/restore {"ids": [...]}` returns `{"reverted": [proposal_json], "left": [...],
    "message": summary}`. It returns 409 if the session is in `busy` (2.4), and holds `busy` while it writes so no turn
    can start meanwhile. A partial failure is a 409 carrying `error`, `reverted` and `left`.
  - `rewind` passes `restore` through to the agent.

### Front end: new `static/checkpoints.js`, called from `app.js`

- **`checkpointFor(mid)`** fetches the preview.
- **`confirmRewind(el, kind)`** replaces the two `confirmDialog` calls in `editMessage` and `retryFrom`.
  - With no applied changes, it behaves as today (1.4).
  - Otherwise the dialog shows the list:
    - Each row shows `path #id`, or, when the change can't be undone, `path #id: changed since, left as is` in muted
      text.
    - A checkbox "Also undo these N file changes", ticked by default.
    - The footnote: "Changes from commands, the terminal or other editors aren't undone." (1.7)
  - It returns `{ok, restore: ids}`.
  - For the *last* message today's flow has no dialog. The dialog now appears there too, but only when applied changes
    exist (1.1).
- **`markTurn`** adds a third hover button (↶ "Undo file changes from here") to the existing `.msg-actions`. The button
  is hidden until a preview shows at least one change that can be undone. The preview is fetched on hover, at most
  once every 3 seconds per message: later turns can apply more, so it can't be cached for good.
- **If undoing fails partway during Edit/Retry:** the page has already removed the later messages, but the server kept
  them (3.4). No turn starts, so the new bubble never gets its message id. `afterRestoreRewind` sees that, redraws the
  conversation from the server (`openSession`) and shows the error as a toast.
- **After a restore:**
  - Update `state.proposals`.
  - Call `refreshProposalViews`, `loadGit()` and `reloadOpenFiles()`, exactly as `undoCommand` does.

Wording follows the existing dialogs ("Rewind to this message?"). The checkbox reuses the `.toggle` style from the
composer.

## Data models

`proposals.applied_at REAL` (additive migration). Proposal status `reverted` already exists, and
`STATUS_TIPS.reverted` already says "Undone".

The browser sends `{restore: [ids], keep: [ids]}` with a rewind and `{ids, keep}` to `/restore`. Every await in
`checkpoints.js` re-checks that the same session and message are still on screen, so a late answer never acts on
another session. A failed preview request aborts Edit/Retry with an error, rather than counting as "no changes".

## Error handling

- The message was compacted (archived): `rewind` already refuses with its existing message.
- A message id from another session: `since` returns `[]` (`Store.message_created(mid, sid)`).
- A change that is no longer applied (already undone with `/undo`): listed as "no longer applied", and it doesn't block
  older changes to the same file.
- The file was deleted by the user: preview reports "changed since" (the expected content isn't `None`).
- The file was recreated after a change that created it: also "changed since". The guard never deletes your file.
- A write fails partway: `RestoreError`. The chat shows which files were restored, and the conversation is left as is
  (3.4).
- A stale preview (something was applied between preview and confirm): `restore` acts only on the ids that were
  shown, re-checked against the disk (3.3).

## Testing strategy

- **`tests/test_checkpoints.py`** (new):
  - `since` ordering and the timestamp boundary.
  - `preview` with one change, several changes to one file, a created file, a file edited after apply (1.5), and a
    blocked newer change hiding older ones (3.2).
  - `restore` acts only on the given ids (3.3).
  - An injected failing writer gives a partial result and `RestoreError` (3.4).
- **`tests/test_queue_rewind.py`:**
  - `rewind(..., restore=[...])` reverts first, then rewinds, and emits `proposal` events and a notice (1.2, 1.6).
  - On `RestoreError` the messages are kept (3.4).
  - Reverted proposals appear in the next `<turn_context>` (2.3).
- **`tests/test_server.py`:**
  - The checkpoint endpoint's JSON.
  - `restore` returns 409 while busy (2.4).
- **`tests/e2e/test_ui.py`**, using the scripted "fix two" turn with auto-apply on:
  - Retrying the first message shows the dialog with two changes and the checkbox ticked. After confirming, the files
    on disk are restored and the proposals show `reverted` (1.1, 1.2).
  - Unticking the checkbox leaves the files as they are (1.3).
  - ↶ undoes the changes without removing messages (2.1, 2.2).
  - Editing a file in between shows "changed since" (1.5).

## Alternatives rejected

- **Snapshots in a shadow git directory at each turn start.** These would also capture changes made by `run_command`,
  but they cost disk and time on large repos, they need care with untracked and ignored files, and they add a second
  undo mechanism next to proposals. Claude Code's checkpoints also cover only the agent's own edits.
- **Storing a turn id on each proposal.** It would be more precise than timestamps, but rewinding already relies on
  timestamps, and two rules for the same question would drift apart.
