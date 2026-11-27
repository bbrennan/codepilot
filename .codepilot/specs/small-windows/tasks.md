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
- [x] 2. The title bar fits a 480px window
  - Test first (Playwright): no sideways scroll and theme and help in view at 600 and 480 wide.
  - `app.css` (the 820px block, and the status bar's items), `index.html` (the word "codepilot" in a span).
  - _Requirements: 1.4_
  - _Tests: tests/e2e/test_window_fit_ui.py (at 600, 561, 559 and 480 wide the page doesn't scroll sideways, every
    title-bar button is on screen at full size with a tooltip, a long folder name keeps 100px, and the word
    "codepilot" shows only above 560)_
- [x] 3. Panes give the editor 440px, and the sidebar steps aside when even that can't fit
  - Test first (Playwright): the editor's width at 1024; `auto-no-sidebar` at 900 and back at 1440; the user's own
    toggle wins until the next resize; saved sizes untouched.
  - `layout.js` (`CENTER_COMFORT`, `CENTER_FLOOR`, `layoutShown`, `layoutSidebarSteps`, `auto-no-sidebar`,
    `layoutUserShowedSidebar`), `app.css` (`.auto-no-sidebar` beside `.no-sidebar`), `app.js` (`showSidebar` from
    `setView`, `toggleSidebar` for the button and ⌘B, the activity bar asks `layoutShown`); `docs/usage.md` (The
    screen), `docs/architecture.md` (`layout.js`).
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Tests: tests/e2e/test_window_fit_ui.py (at 1024×700 the editor keeps 440 with the sidebar and chat at or above
    their minimums, also with an 820px chat saved, which stays saved; the sidebar steps aside at 935 and 821, not at
    936 or 820; at 900 the class and the chat's width settle and stay, and at 1440 the saved sizes are back; showing
    the sidebar by the button, ⌘B, the active or another activity icon wins through opening a file until a resize;
    hiding it yourself is saved and kept; hiding it at 1280 gives the chat what leaves the editor 440, 788px, where
    it used to give the chat its full 820)_
- [x] 4. The Review tab stacks its change list above the diff in a narrow editor
  - Test first (Playwright): at 1024×700 with two changes waiting ("fix two"), the list is above the diff and shorter
    than it, Apply, Reject and Open file are inside the header, and j/k move through the list; just above and at the
    set width, beside and above.
  - `app.css` (an `editor` container query on `.review`).
  - _Requirements: 1.5_
  - _Tests: tests/e2e/test_narrow_panes_ui.py (at 1024×700 with the bottom panel open and two changes waiting, the
    list is above the diff and shorter than it, Apply, Reject and Open file are inside the header and hit-testable,
    and j and k move the selection; with a 641px editor the list is beside the diff, with 640 above it)_
