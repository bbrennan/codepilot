# Tasks

One branch, `feature/restore-tabs`, one PR. Needs `place.js` from ui-review-fixes task 2.

- [x] 1. Tabs, their place and the Explorer's open folders come back
  - Test first (Playwright): reload with files, a spec and Review open; a deleted file; closing a tab; a stale record.
  - `static/tabstate.js` (new: `tabRecord`, `saveTabs`, `restoreTabs`, `pruneTabRecords`), `index.html`, `app.js`
    (the calls in design.md, a `quiet` option on `openTab`).
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.3, 3.4_
  - _Tests: tests/e2e/test_restore_tabs_ui.py (every kind of tab comes back in order with the same one active; a file
    comes back at its line with its selection; Markdown comes back in Preview at its scroll and in Source at its line;
    a tab whose file is gone is left out quietly; a closed tab stays closed; tabs of a folder not opened for 30 days
    are removed; only the 20 most recent folders are kept)_
- [x] 2. Unsaved edits come back
  - Test first (Playwright): a draft after reload; the file changed on disk; the file deleted; a draft too large to
    store asks before leaving.
  - `static/tabstate.js` (drafts, `unsafe`, `beforeunload`), `app.js` (`saveFile` writes a missing file with
    `new_file`).
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Tests: tests/e2e/test_restore_tabs_ui.py (an unsaved edit comes back after a reload and saves; an edit to a file
    changed on disk is kept, said once, and Save asks; an edit to a deleted file comes back and Save writes the file
    again; a draft too large to store, and storage that is full, ask before the page is left; a stored draft leaves
    without asking; a discarded edit stays discarded)_
- [x] 3. Each folder keeps its own tabs
  - Test first (Playwright): two sessions on two folders, and two on one.
  - `app.js` (`setWorkspace`: save before the tabs are dropped, restore after); `docs/usage.md` (The screen, Files and
    folders: what comes back, and the two-window limit), `docs/architecture.md` (script list).
  - _Requirements: 3.1, 3.2_
  - _Tests: tests/e2e/test_restore_tabs_ui.py (each folder keeps its own tabs and drafts, switching at once after
    typing; sessions on one folder share its tabs; Review comes back only for a session with changes)_
