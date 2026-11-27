# Tasks

One branch, `feature/small-windows`, one PR. After ui-review-fixes task 1.

- [x] 1. Toolbars show icons when there's no room for words
  - Test first (Playwright): at 1024×700 every editor and terminal toolbar button is inside its bar and has a tooltip;
    panel tabs stay on one line.
  - `app.css` (the two containers and their queries), `app.js`, `specs-quick.js` and `index.html` (`.lbl` spans,
    titles and icons; no new logic).
  - _Requirements: 1.1, 1.2, 1.3_
  - _Tests: tests/e2e/test_narrow_panes_ui.py (every editor toolbar, file, markdown Source and Preview, editing,
    trace, binary and spec, keeps every control inside its bar and hit-testable with a tooltip at 641, 639, 521, 519,
    421, 419 and 280px, words shown or hidden as measured; the terminal's toolbar at 421, 419 and 280; the panel's
    tabs one line each at 280 with Clear and Close reachable; at 1024×700 the file and terminal toolbars, the words
    still naming the buttons)_
- [ ] 2. The title bar fits a 480px window
  - Test first (Playwright): no sideways scroll and theme and help in view at 600 and 480 wide.
  - `app.css` (the 820px block).
  - _Requirements: 1.4_
- [ ] 3. Panes give the editor 440px, and the sidebar steps aside when even that can't fit
  - Test first (Playwright): the editor's width at 1024; `auto-no-sidebar` at 900 and back at 1440; the user's own
    toggle wins until the next resize; saved sizes untouched.
  - `layout.js` (`CENTER_COMFORT`, `CENTER_FLOOR`, `auto-no-sidebar`, `layoutUserShowedSidebar`), `app.css`
    (`.auto-no-sidebar` beside `.no-sidebar`), `app.js` (two calls); `docs/usage.md` (The screen).
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
- [ ] 4. The Review tab stacks its change list above the diff in a narrow editor
  - Test first (Playwright): at 1024×700 with two changes waiting ("fix two"), the list is above the diff and shorter
    than it, Apply, Reject and Open file are inside the header, and j/k move through the list; just above and at the
    set width, beside and above.
  - `app.css` (an `editor` container query on `.review`).
  - _Requirements: 1.5_
