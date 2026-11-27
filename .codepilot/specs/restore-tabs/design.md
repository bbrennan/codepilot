# Design

## What is stored

One record per main folder in `localStorage`, key `cp-tabs:<absolute folder path>`:

```json
{ "v": 1, "at": 1795736100, "active": "file:agent/core.py", "expanded": ["agent", "web/src"],
  "tabs": [ { "id": "file:agent/core.py", "kind": "file", "path": "agent/core.py", "view": "source", "topLine": 120,
              "sel": { "a": 5, "b": 10 }, "caret": 2210, "editing": true,
              "draft": "…the unsaved text…", "baseMtime": "1795730000000000000" },
            { "id": "spec:csv-export", "kind": "spec", "name": "csv-export" } ] }
```

Per folder, not per session: `state.tabs` is already one list that sessions on the same folder share, and
`setWorkspace(repo, changed)` already empties the file tabs when the folder changes. File contents are never stored;
only a draft is, and only while it differs from the file. `topLine` is the shared place from `place.js`
(ui-review-fixes, task 2).

## Module: `static/tabstate.js` (new, loaded after `app.js`)

- `tabRecord(tab)` → the stored form, or `null` for kinds that aren't restored (a proposal's own diff tab, global
  steering docs). A table of kinds maps each to its fields and its reopen function (`openFile`, `openTrace`,
  `openSpec`, `openReview`, `openGitDiff`), so a new tab kind is restored by adding a row.
- `saveTabs()` writes the current folder's record. `saveTabsSoon = debounce(saveTabs, 300)`. A draft over 1 MB, or a
  write that throws (quota, blocked storage), leaves that tab's id in `unsafe`, a Set; a successful write clears it.
- `restoreTabs(repo)`: reads the record, sets `state.expanded`, then reopens each tab in order with its reopen
  function, without activating them one by one (a `quiet` option on `openTab`), and finally sets `state.active` and
  renders once. It checks `state.workspace === repo` after each await, as `openSession` does for its session.
- Drafts: after `openFile` loads the tab, a stored draft sets `tab.editing = true`, `tab.draft`, `tab.dirty`. If the
  file's `mtime` differs from `baseMtime`, the tab keeps `tab.mtime = baseMtime` (so Save meets the existing "changed on
  disk" confirmation) and one toast says "…changed on disk since your unsaved edit". If the file is gone (404), the tab
  opens from the draft alone with `tab.missing = true`; `saveFile` then uses the `new_file` operation with the content.
- `pruneTabRecords()` at startup: drop records whose `at` is over 30 days old; keep at most 20.
- `beforeunload`: `preventDefault()` only when `unsafe` holds a tab that is still dirty (2.4).

## Wiring in `app.js` (calls only)

| Where | Call |
|---|---|
| end of `renderEditor`, `setDirty`, the editor's `oninput`, `closeTab`, the tree's expand/collapse | `saveTabsSoon()` |
| `setWorkspace` when `changed`: **before** the tabs are filtered | `saveTabs()` for the folder being left |
| `setWorkspace` when `changed`: after `renderTree()` | `restoreTabs(repo)` |
| `pagehide` and `visibilitychange` (hidden) | `saveTabs()` (flush the debounce) |
| `init` | `pruneTabRecords()` |

`setWorkspace` runs on first load too (from `openSession`), so one path restores in every case.

## Decisions

- **Stored in the browser, not the server.** It is this window's state, like pane sizes and the theme. The app window
  has its own Chrome profile (#66), so the record lives as long as that profile.
- **No prompt when the edit is stored.** A prompt on every reload with a dirty tab would train you to click through it.
- **Two windows on one folder: last writer wins.** The record is rewritten whole. Unsaved edits typed in one window can
  be replaced by the other window's record; listed in docs as a limit.
- **Closing a dirty tab still asks** (existing `confirmDialog`): closing is a decision, a reload isn't.

## Tests

`tests/e2e/test_restore_tabs_ui.py` (new):
- three files, a spec and the Review tab open, the second file active and scrolled to line 80: after `page.reload()`,
  the same tabs, order, active tab and top line; the Explorer's open folders (1.1, 1.2, 1.4);
- a file deleted on disk before the reload is left out with no toast and no console error (1.3);
- typed, unsaved text is back after a reload, the tab is dirty, and Save writes it (2.1);
- the file edited on disk before the reload: the draft is kept, Save asks, Overwrite writes the draft (2.2);
- the file deleted before the reload: the draft is shown, Save recreates the file (2.3);
- a 1.2 MB draft: `beforeunload` is cancelled (assert through a `dialog` handler); a small one: no dialog (2.4);
- two sessions on two folders: switch away and back, tabs and a draft return; a second session on the first folder
  shows the first one's tabs (3.1, 3.2);
- closing a tab and reloading: it stays closed; Discard and reload: the file's own text (3.3);
- a record with `at` 31 days ago is gone after load (3.4, set through an init script).
