# Tasks

One branch and PR per numbered task, merged before the next starts. Every sub-task is test first, in
`tests/e2e/test_keyboard_access_ui.py`, driving the keyboard only.

- [x] 1. Rows and links you can click are reachable (`feature/keyboard-rows`)
  - [x] 1.1 `a11y.js` with `ACTIVATABLE`: focusable, named, and Enter or Space activates
    - `static/a11y.js` (new), `index.html`, `app.css` (a row's own buttons shown on `:focus-within`); no change to
      render functions.
    - _Requirements: 4.1, 4.2_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (Tab reaches a search file row and hit, both buttons, and Enter opens
      the hit at its line with focus left on it; Space opens a changed file; Enter opens a session and focus is on its
      row in the redrawn list, never on the body; Enter on a session's Delete deletes it without opening it, focus then
      on the list's first row; a path in a reply is a link Enter opens; Enter on a proposed change opens it in Review;
      in Review, Enter selects a row and focus follows the selection through k, never on the body; the welcome page's
      Go to file and the context meter; a spec and a steering doc open from their lists)_
  - [x] 1.2 The audit test: nothing clickable is unreachable
    - Welcome, a file open, Changes, Search with hits, a chat with steps and a change, Review, Sessions, Steering;
      it lists what it finds by tag, id, classes, `data-*` and container, so a failure names the element. The tree,
      the line numbers and the tabs are allowed by name until tasks 2 and 3.
    - _Requirements: 4.5_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (on those eight screens nothing with a pointer or grab cursor lacks a
      focusable self or ancestor, a label around a switch excepted; a focused row's ring is the 2px accent at 3:1 or
      more against the row, selected or not, in both themes)_
  - [x] 1.3 A message's Edit, Retry and Undo by keyboard
    - `app.css` (`.msg-actions` shown on hover and focus-within), `app.js` (labels on the three buttons).
    - _Requirements: 4.3_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (the actions are transparent until Tab reaches Edit, then shown;
      Edit and Retry are named; Enter on Retry sends the message again)_
  - [x] 1.4 (added) In a short stacked Review list, j, k and the arrows keep the selected change in view
    - `app.js` (`renderReviewTab`: one line).
    - _Requirements: 4.1_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (at 1024×700 with twelve changes, eleven j presses each leave the
      selected row inside the list)_
- [ ] 2. The file tree (`feature/keyboard-tree`)
  - [ ] 2.1 One Tab stop, arrows, Home, End, Enter, Space, typeahead
    - `a11y.js` (`roving`, `treeKeys`, `treeRendered`), `app.js` (`renderTree` ends with one call).
    - _Requirements: 1.1, 1.2, 1.3_
  - [ ] 2.2 F2, Delete, ⌘C and the context menu on the focused row; focus survives a redraw
    - `app.js` (remove `treeFocused`; its two `keydown` branches move to `treeKeys`), `app.css` (the picked row's
      outline only while the tree has focus).
    - _Requirements: 1.4, 1.5_
- [ ] 3. Tabs, menus and regions (`feature/keyboard-tabs-menus`)
  - [ ] 3.1 Editor tabs and panel tabs as tab lists; the close button's name
    - `a11y.js` (`tabsRendered`), `app.js` (`renderTabs`: one attribute, one call; `showPanelTab`: one call).
    - _Requirements: 2.1, 2.2, 2.3_
  - [ ] 3.2 Activity bar state and names; the chat title's name
    - `a11y.js` (`viewChanged`), `app.js` (`setView`, `renderProposalList`), `progress.js` (its badge), `sessions.js`.
    - _Requirements: 2.3, 2.4_
  - [ ] 3.3 Menus take focus, move with arrows and give focus back
    - `a11y.js` (`menu`), `app.js` (`showMenu` ends with one call; `aria-haspopup` on the five menu buttons).
    - _Requirements: 3.1, 3.2_
  - [ ] 3.4 F6 moves between sidebar, editor, panel and chat
    - `a11y.js` (`regions`), `index.html` (landmark labels); `docs/usage.md` (Keyboard shortcuts).
    - _Requirements: 2.5_
- [ ] 4. Dialogs and suggestion lists (`feature/keyboard-dialogs`)
  - [ ] 4.1 Dialogs: role, focus in, Tab stays in, Escape, focus back
    - `a11y.js` (`modal`, the `hidden` observer), `app.js` (`#folderDialog` Escape).
    - _Requirements: 3.3, 3.4_
  - [ ] 4.2 A destructive confirmation focuses Cancel
    - `app.js` (`confirmDialog`); update any test that confirmed with Enter.
    - _Requirements: 3.5_
  - [ ] 4.3 The @, / and # lists say which option is current
    - `a11y.js` (`mentionsRendered`), `app.js` (`renderMentions`: one call).
    - _Requirements: 4.4_
- [ ] 5. Announcements (`feature/keyboard-announce`)
  - [ ] 5.1 Toasts, and a turn that finishes, needs approval or fails
    - `a11y.js` (`announce`, `turnState`), `index.html` (the two live regions), `app.css` (`.sr-only`), `app.js`
      (`toast`, `updateBusy`, three `render` branches: one call each).
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ] 5.2 Docs
    - `docs/usage.md` (Keyboard shortcuts: the tree, tabs, menus, F6), `docs/architecture.md` (script list).
    - _Requirements: 1.1, 2.1, 2.5_
