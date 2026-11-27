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
- [x] 2. The file tree (`feature/keyboard-tree`)
  - [x] 2.1 One Tab stop, arrows, Home, End, Enter, Space, typeahead
    - `a11y.js` (the tree's roles, tab stop and keys, `treeRendered`), `app.js` (`renderTree` ends with one call).
    - _Requirements: 1.1, 1.2, 1.3_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (one Tab in from the Explorer's toolbar lands on the first row, a
      `treeitem` at level 1, closed; the tree has one tab stop and one Tab leaves it; Right opens agent/, Right again
      goes into it at level 2, Enter opens core.py with focus left in the tree, Left goes to the folder and Left again
      closes it; End, Home, Down, Up; Space opens a folder; typing "re" finds README.md, and after a pause "r" finds the
      next "r")_
  - [x] 2.2 F2, Delete, ⌘C and the context menu on the focused row; focus survives a redraw
    - `a11y.js` (the tree's own `keydown`), `app.js` (`treeFocused` and the global F2, Delete and ⌘C branches removed;
      `reviewKeys` acts only from the Review or the page; the bar's Review button puts focus on the selected change),
      `app.css` (the picked row's outline only while the tree has focus).
    - _Requirements: 1.4, 1.5_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (F2 on the focused row asks to rename it, Delete to delete it; ⌘C
      copies its path and does nothing with focus elsewhere; Shift+F10 opens its menu at the row; a file created on disk
      redraws the tree and focus stays on the same path, never on the body; with Review active and focus in the tree,
      "a", "r" and Down change nothing in Review, and j works again from the page; Enter on the bar's Review button puts
      focus on the selected change, where "a" applies it)_
  - [x] 2.3 (added: the audit found it) The code view's line numbers by keyboard
    - `a11y.js` (the gutter as a listbox with an active line), `app.css` (the line you're on).
    - _Requirements: 4.5_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (the line numbers are one tab stop; Down twice and Enter selects
      line 3 with focus kept, Shift+Enter extends to 5, End goes to line 40 and Space selects it, scrolled into view;
      the audit no longer allows the tree or the line numbers)_
- [x] 3. Tabs, menus and regions (`feature/keyboard-tabs-menus`)
  - [x] 3.1 Editor tabs and panel tabs as tab lists; the close button's name
    - `a11y.js` (`tabsRendered`, `panelTabsShown`, the strips' keys; a click on a tab leaves focus on the page),
      `app.js` (`renderTabs`: one attribute, one call; `showPanelTab`: one call), `index.html` (the panel's tabs in
      their own tablist, with ids, `aria-controls` and tab panels), `app.css` (`.ptabs`).
    - _Requirements: 2.1, 2.2, 2.3_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (from the tree, Tab lands on the shown tab, a selected `tab` in a
      `tablist` over a `tabpanel`; Left, Home and End move and show it with focus following; Delete closes it and focus
      lands on the tab shown next; one Tab leaves the strip; close buttons are named "Close <title>"; Delete on a tab
      with unsaved edits asks first; tabs reopened after a reload don't take focus; the panel's tabs are a "Panel"
      tablist where Right shows Output with focus on its tab, and one Shift+Tab leaves it; the audit allows nothing),
      tests/e2e/test_review_ui.py (after a click on the Review tab, j still moves the list)_
  - [x] 3.2 Activity bar state and names; the chat title's name
    - `a11y.js` (`viewChanged`, asking `layoutShown`; the chat title watched), `app.js` (`setView`,
      `renderProposalList`: one call each), `index.html` (badges hidden from assistive technology). `progress.js` and
      `sessions.js` unchanged: Progress already names its count.
    - _Requirements: 2.3, 2.4_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (Explorer is pressed, nothing when ⌘B hides the sidebar, Explorer
      again when shown, then Search; Changes is named "Changes, 1 waiting for review" and its badge is hidden; at 900
      wide, where the sidebar steps aside, nothing is pressed; the chat title is "Switch session: <title>")_
  - [x] 3.3 Menus take focus, move with arrows and give focus back
    - `a11y.js` (`menu`, the opener tracked outside overlays, focus back when the menu hides), `app.js` (`showMenu`
      ends with one call), `index.html` (`aria-haspopup` and `aria-expanded` on the six menu buttons).
    - _Requirements: 3.1, 3.2_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (Enter on File opens a `menu` with focus on New File… and the button
      expanded; Down, End, Down round to the top, "o" finds Open Folder…; Escape closes it with focus back on File,
      collapsed; Shift+F10 on a tree row focuses Open, "c" finds Copy relative path, Enter copies it and focus is back
      on the row)_
  - [x] 3.4 F6 moves between sidebar, editor, panel and chat
    - `a11y.js` (the panes, asking `layoutShown`), `index.html` (landmark labels); `docs/usage.md` (Keyboard shortcuts:
      F6, the Explorer, tabs, menus, line numbers, where Review's keys act).
    - _Requirements: 2.5_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (from the message box F6 goes to the tree, then the shown tab, then
      skips the closed panel back to the message box; Shift+F6 goes back; with the panel open it's included; with the
      sidebar hidden it's skipped; the landmarks are named Views, Sidebar, Editor, Panel, Chat and Status)_
- [x] 4. Dialogs and suggestion lists (`feature/keyboard-dialogs`)
  - [x] 4.1 Dialogs: role, focus in, Tab stays in, Escape, focus back
    - `a11y.js` (the four dialogs, the `hidden` observer, the opener tracked outside overlays, focus back after the
      closing key; the folder dialog's list and places), `app.js` (the folder dialog lets Enter on a place through),
      `index.html` (ids on two headings). `#folderDialog` already closed on Escape from anywhere inside.
    - _Requirements: 3.3, 3.4_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (Add folder… from the folder menu opens a named modal dialog with focus
      inside; 30 Tabs and 5 Shift+Tabs never leave it; Escape gives focus back to the folder button; in its list Down
      selects as a click does and Enter goes in, focus staying inside; a place is a button Enter goes to; F2's prompt is
      named, Shift+Tab goes round to OK, Escape from Cancel closes it and focus is back on the row, where Delete then
      works; Go to file and Report a problem are named dialogs that give focus back to the tree and the message box;
      Enter in a prompt opened from New Folder by keyboard doesn't open it a second time)_
  - [x] 4.2 A destructive confirmation focuses Cancel
    - `app.js` (`confirmDialog`). No browser test confirmed one with Enter: they click `#dialogOk` or answer a prompt
      in its text box, which is unchanged.
    - _Requirements: 3.5_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (Delete on a row opens the confirmation on Cancel; Enter cancels and
      the file stays, focus back on the row; Delete again, Tab to Delete, Enter deletes it)_
  - [x] 4.3 The @, / and # lists say which option is current
    - `a11y.js` (the list observed: three functions draw it), no change to `app.js`.
    - _Requirements: 4.4_
    - _Tests: tests/e2e/test_keyboard_access_ui.py (typing "@a" opens a listbox whose current option is selected and is
      the message box's active descendant, with `aria-controls` and `aria-autocomplete`; Down moves it; Escape clears
      it; the same for "/he")_
- [ ] 5. Announcements (`feature/keyboard-announce`)
  - [ ] 5.1 Toasts, and a turn that finishes, needs approval or fails
    - `a11y.js` (`announce`, `turnState`), `index.html` (the two live regions), `app.css` (`.sr-only`), `app.js`
      (`toast`, `updateBusy`, three `render` branches: one call each).
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ] 5.2 Docs
    - `docs/usage.md` (Keyboard shortcuts: the tree, tabs, menus, F6), `docs/architecture.md` (script list).
    - _Requirements: 1.1, 2.1, 2.5_
