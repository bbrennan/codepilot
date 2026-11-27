# Tasks

One branch, `feature/small-windows`, one PR. After ui-review-fixes task 1.

- [ ] 1. Toolbars show icons when there's no room for words
  - Test first (Playwright): at 1024×700 every editor and terminal toolbar button is inside its bar and has a tooltip;
    panel tabs stay on one line.
  - `app.css` (the two containers and their queries), `app.js` and `index.html` (`.lbl` spans and titles; no new
    logic).
  - _Requirements: 1.1, 1.2, 1.3_
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
