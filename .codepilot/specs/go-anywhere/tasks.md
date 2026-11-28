# Tasks

One branch, `feature/go-anywhere`, one PR. After ui-review-fixes task 8 (`keys.js`).

- [x] 1. The palette moves to its own script
  - No behaviour change: the existing Go-to-file tests pass before and after.
  - `static/palette.js` (new: `pal`, `openPalette`, `palSearch`, `renderPalette`, `closePalette` and their listeners,
    moved unchanged), `index.html`, `app.js` (the block removed; the welcome page's `#wFind` calls `openPalette` through
    a wrapper, as the function now loads after `app.js`).
  - _Requirements: 1.3_
  - _Tests: unchanged and passing before and after the move: tests/e2e/test_multi_folder_ui.py (a file in an added
    folder), test_keyboard_access_ui.py (the palette is a dialog that gives focus back, the welcome page's Go to file,
    the File menu's Go to File…, a file gone by the time it opens, the audit), test_code_editor_ui.py (⌘P from inside
    the editor), test_design_tokens_ui.py (the palette's focus ring), test_chat_input_ui.py (Ctrl+V on a Mac)_
- [x] 2. Recent files, and `name:line`
  - Test first (Playwright): the recent order and the two-file switch; a deleted recent file; `core.py:2`; `:1`.
  - `palette.js` (modes table, `fileItems`, `recentFiles`, `noteRecent`, `lineItems`, `palGoTo`; the list a listbox
    with headings), `app.js` (`renderEditor`: one call), `editor.js` (`goToLine` on the handle), `tabstate.js`
    (`pruneTabRecords` takes the key prefix), `index.html` (the combobox's roles), `app.css`.
  - _Requirements: 1.1, 1.2, 1.3_
  - _Tests: tests/e2e/test_palette_ui.py (an empty ⌘P lists the files you were in, the one before on top, and ⌘P,
    Enter switches two files; the current option is the box's active descendant and a heading names its group; a file
    deleted on disk isn't listed; the list survives a reload; each folder has its own, also across a session switch;
    redrawing the same file writes nothing; folders not opened for 30 days, and all but the 20 most recent, are
    forgotten; a recent file in an added folder opens, and is left out once the folder is removed; `long.py:40` opens
    with line 40 flashed; `:60` goes to line 60 in the file shown; `:5` with no file lists nothing; in Edit mode `:50`
    and `long.py:20` move the caret, keep the draft and leave focus in the editor; the handle's `goToLine`, past the
    end too; with no folder ⌘P opens and says to open one)_
- [ ] 3. Commands
  - Test first (Playwright): `>` filtering, key labels, Enter runs, ⇧⌘P, `when`, the list in 2.3, a registered command.
  - `palette.js` (`registerCommand`, `commandItems`, the built-in registrations), `app.js` (one `keydown` branch).
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
- [ ] 4. Sessions, the placeholder and docs
  - Test first (Playwright): a matching session is listed under its heading and opens.
  - `palette.js` (`sessionItems`), `index.html` (placeholder); `docs/usage.md` (The screen, Keyboard shortcuts),
    `docs/architecture.md` (script list).
  - _Requirements: 3.1, 3.2, 3.3_
