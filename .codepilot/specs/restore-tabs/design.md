# Design

## What is stored

One record per main folder in `localStorage`, key `cp-tabs:<absolute folder path>`:

```json
{ "v": 1, "at": 1795736100, "active": "file:agent/core.py", "expanded": ["agent", "web/src"],
  "tabs": [ { "id": "file:agent/core.py", "kind": "file", "path": "agent/core.py", "view": null, "topLine": 120,
              "scroll": 0, "sel": { "a": 5, "b": 10 }, "caret": 2210, "editing": true, "editPreview": false,
              "draft": "…the unsaved text…", "baseMtime": "1795730000000000000" },
            { "id": "spec:csv-export", "kind": "spec", "name": "csv-export", "view": null },
            { "id": "review", "kind": "review", "sel": 12 } ] }
```

Per folder, not per session: `state.tabs` is already one list that sessions on the same folder share. File contents
are never stored; only a draft is, and only while it differs from the file (a file that isn't UTF-8, `tab.encoding`,
can't be edited, so it never has one). `topLine` is the shared place from `place.js` (ui-review-fixes, task 2) for the
code view and the editor; a Markdown Preview keeps its own place in pixels as `tab.scroll`, so both are stored.

**Whose tabs are whose.** Every kind that names something in the folder belongs to the folder: file, image, binary,
trace, spec and the working-tree diff (`gitdiff`). The Review tab belongs to the session: it is stored in its place
among the folder's tabs, and comes back only when the session now open has changes to show. When the folder changes,
all the tabs are replaced by the new folder's (before this, `setWorkspace` dropped only file, trace and gitdiff tabs,
so images, binaries, specs and Review carried into the next folder).

## Module: `static/tabstate.js` (new, loaded after `app.js`)

- `TAB_KINDS`: a table of the seven kinds, mapping each to what is stored for it and its reopen function, so a new tab
  kind is restored by adding a row. File, image and binary tabs all reopen through `openFile`, which works out the kind
  again; traces through `openTrace`, specs `openSpec`, Review `openReview`, the diff `openGitDiff`. A kind not in the
  table isn't restored, nor is a file-kind tab that isn't `file:<path>` (global steering docs, another tool's read-only
  steering file).
- `tabRecord(tab, unsafe)` → the stored form, or `null`.
- `saveTabs()` writes the record of `tabStore.folder`: the folder whose tabs `state.tabs` holds, not
  `state.workspace` (which `openSession` has already moved on when `setWorkspace` runs). It writes nothing while tabs
  are being restored, so a half-restored list never replaces a full one. `saveTabsSoon = debounce(saveTabs, 300)`. A
  draft over 1,000,000 characters is left out and its tab id goes into `unsafe`; a write that throws (quota, blocked
  storage) puts every dirty tab in `unsafe` and retries without drafts, so the tabs and their place still come back.
  Each write recomputes `unsafe`.
- `restoreTabs(repo)` replaces the tabs with the folder's. Before it awaits anything it empties `state.tabs` and sets
  `state.expanded` from the record, so the tree `setWorkspace` draws next is already open in the right places (a
  folder that's gone isn't in its parent's listing, so it is never asked for). Then one `/stat` call says which files
  still exist (and their mtimes), `/traces` which traces, and `loadSpecs` which specs, so nothing gone is requested
  (that would toast an error and log a 404). Each tab is reopened in order with its reopen function, without being
  shown one by one: `openTab(tab, quiet = tabsRestoring())`. A place is set on the tab before the one render, never
  passed to `openFile` as a line (`openFile(path, line)` sets the place once, through `jumpTop`: a line would flash it
  and clear the selection). At the end the tabs are put in the record's order, `state.active` is set and the editor is
  drawn once. A newer restore takes over from an older one; while a session is opening, `state.workspace` is briefly
  `null`, and the restore waits for it to settle rather than give up (a session on the same folder keeps its tabs and
  doesn't restore again).
- Drafts: after `openFile` loads the tab, a stored draft sets `tab.editing = true`, `tab.draft`, `tab.dirty`, and
  `tab.mtime = baseMtime`. If the file changed since, Save then meets the existing "changed on disk" confirmation, and
  `checkDisk` already says so once ("…changed on disk. Your unsaved edits are kept; saving will ask before
  overwriting."): the restore adds no message of its own, which would make two within two seconds. If the file is
  gone, the tab opens from the draft alone with `tab.missing = true` and `mtime: null` (which `checkDisk` skips), and
  the restore says once that it was deleted and the edit is kept; `saveFile` then uses the `new_file` operation with the
  content.
- `pruneTabRecords()` at startup: drop records whose `at` is over 30 days old; keep at most 20.
- Its own listeners: `beforeunload` writes (the debounce may not have run) and calls `preventDefault()` only when
  `unsafe` holds a tab that is still dirty (2.4); `pagehide` and `visibilitychange` (hidden) write.

## Wiring in `app.js` (calls only)

| Where | Call |
|---|---|
| start of `renderEditor` (it returns early when no tab is open), covering tab switches, `closeTab`, Done and Discard | `saveTabsSoon()` |
| `setDirty` (the editor's `oninput` calls it) | `saveTabsSoon()` |
| end of `renderTree`, covering expand, collapse and Collapse all | `saveTabsSoon()` |
| `setWorkspace` when `changed`: **before** the tree and tabs are cleared | `saveTabs()` for the folder being left |
| `setWorkspace` when `changed`: **before** `renderTree()` | `restoreTabs(repo)` (replaces the old filter) |
| `openTab` | a `quiet` parameter, defaulting to `tabsRestoring()` |
| `saveFile` | `new_file` with the content for a `missing` tab; clears `missing` once saved |
| `init`, after its first `await` (the scripts after `app.js` have loaded by then) | `pruneTabRecords()` |

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
- two files, an image, a binary file, a trace, a spec, the Review tab and the working-tree diff open, the second file
  active: after `page.reload()`, the same tabs, kinds, order and active tab, and the Explorer's open folders (1.1, 1.4);
- a file at line 80 with lines 85–90 selected comes back there, with nothing flashing; a Markdown file in Preview
  comes back in Preview at its scroll, another in Source at its line (1.2);
- a file deleted on disk before the reload is left out with no toast and no console error (1.3);
- typed, unsaved text is back after a reload, the tab is dirty, and Save writes it (2.1);
- the file edited on disk before the reload: the draft is kept, one toast says so, Save asks, Overwrite writes the
  draft (2.2);
- the file deleted before the reload: the draft is shown, one toast says it was deleted, Save recreates the file (2.3);
- a 1.2 MB draft (`fill`, then a real click: Chrome asks only on a page that was used), and storage that throws on
  write: `beforeunload` is cancelled (assert through a `dialog` handler); a stored draft: no dialog (2.4);
- two sessions on two folders, a draft typed and the session switched at once (inside the debounce): switch away and
  back, the tabs and the draft return, and the first folder's image, spec and Review don't carry into the second; a
  second session on the first folder shows the first one's tabs, after a reload too (3.1, 3.2);
- Review comes back after a reload for a session with changes, not for one without;
- closing a tab and collapsing the tree, then reloading: it stays closed; Discard and reload: the file's own text (3.3);
- a record with `at` 31 days ago is gone after load, one 29 days old is kept; of 25 records the 20 newest are kept
  (3.4, set through an init script).
