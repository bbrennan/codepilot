# Tasks

One branch and PR per numbered task, merged before the next starts. Every sub-task is test first, in
`tests/e2e/test_keyboard_access_ui.py`, driving the keyboard only.

- [ ] 1. Rows and links you can click are reachable (`feature/keyboard-rows`)
  - [ ] 1.1 `a11y.js` with `ACTIVATABLE`: focusable, named, and Enter or Space activates
    - `static/a11y.js` (new), `index.html`; no change to render functions.
    - _Requirements: 4.1, 4.2_
  - [ ] 1.2 The audit test: nothing clickable is unreachable
    - The six screens in design.md; it lists what it finds by selector, so a failure names the element.
    - _Requirements: 4.5_
  - [ ] 1.3 A message's Edit, Retry and Undo by keyboard
    - `app.css` (`.msg-actions` shown on hover and focus-within), `app.js` (labels on the three buttons).
    - _Requirements: 4.3_
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
