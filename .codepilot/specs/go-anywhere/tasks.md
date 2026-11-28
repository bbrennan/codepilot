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
- [ ] 2. Recent files, and `name:line`
  - Test first (Playwright): the recent order and the two-file switch; a deleted recent file; `core.py:2`; `:1`.
  - `palette.js` (modes table, `fileItems`, `recentFiles`, `noteRecent`, `lineItems`), `app.js` (`renderEditor`: one
    call; `openPalette` without a folder).
  - _Requirements: 1.1, 1.2, 1.3_
- [ ] 3. Commands
  - Test first (Playwright): `>` filtering, key labels, Enter runs, ⇧⌘P, `when`, the list in 2.3, a registered command.
  - `palette.js` (`registerCommand`, `commandItems`, the built-in registrations), `app.js` (one `keydown` branch).
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
- [ ] 4. Sessions, the placeholder and docs
  - Test first (Playwright): a matching session is listed under its heading and opens.
  - `palette.js` (`sessionItems`), `index.html` (placeholder); `docs/usage.md` (The screen, Keyboard shortcuts),
    `docs/architecture.md` (script list).
  - _Requirements: 3.1, 3.2, 3.3_
