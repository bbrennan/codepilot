# Tasks

Each task is its own branch from `develop` and its own PR, merged before the next starts. Test first: write the test
named in design.md, watch it fail for the reason in bugfix.md, then fix.

- [x] 1. Stop, Steer and Queue stay inside the message box, and ⌘. stops (`fix/stop-visible`)
  - Test first (Playwright): containment at chat widths 300, 380 and 440 and two window sizes; the key.
  - `index.html` (the two groups), `app.css`, `app.js` (placeholder text, one `keydown` branch); `docs/usage.md`
    (Keyboard shortcuts, Talking to it).
  - _Requirements: 1.1, 1.2, 1.3_
  - _Tests: tests/e2e/test_chat_input_ui.py (Stop, Steer and Queue inside the message box at chat widths 300–440 and
    windows 1024×700 and 1440×900; ⌘. stops the running turn)_
- [ ] 2. Edit and Done keep your place (`fix/edit-keeps-place`)
  - Test first (Playwright): a 300-line file; from the top, from line 120, Done, and across a tab switch.
  - `static/place.js` (new), `index.html`, `app.js` (`renderFileTab`, `renderEditTab`, `checkDisk`);
    `docs/architecture.md` (script list).
  - _Requirements: 2.1, 2.2, 2.3_
- [ ] 3. The active tab is always in view (`fix/active-tab-in-view`)
  - Test first (Playwright): twelve files open in a 1024px window; the Review tab opening; the wheel.
  - `app.js` (`renderTabs`, one listener).
  - _Requirements: 3.1, 3.2_
- [ ] 4. A step that waits says so, and a denied one says it didn't run (`fix/step-wording`)
  - Test first (Playwright): waiting, approved and denied rows, live and after a reload.
  - `steps.js` (`WAITING_TEXT`, `stepWaiting`, `stepApproved`, `stepDenied`), `app.js` (three calls), `app.css` (the two
    row states); `docs/usage.md` (Approvals).
  - _Requirements: 4.1, 4.2, 4.3_
- [ ] 5. Binary files and files that aren't UTF-8 open as what they are (`fix/binary-files`)
  - Test first (unit): `textfile.kind`; the `files` endpoint's two answers. (Playwright): no Edit on either.
  - `textfile.py`, `server.py` (wiring), `static/filekinds.js` (new), `index.html`, `app.js` (`openFile`,
    `renderEditor`, `renderFileTab` wiring); `docs/usage.md` (Files and folders), `docs/architecture.md`.
  - _Requirements: 5.1, 5.2_
- [ ] 6. The Review header holds together, and change notes show no prompt text (`fix/review-header`)
  - Test first (Playwright): the header's buttons share a line from 280px to 660px; a change made in a file with
    file-matched steering shows no `<steering` in its row.
  - `app.js` (`renderReviewTab` markup), `app.css`, `steps.js` (`readerNote`).
  - _Requirements: 6.1, 6.2_
- [ ] 7. Text tokens meet contrast in both themes (`fix/contrast`)
  - Test first (Playwright): compute WCAG contrast for each text token on each surface from the computed styles.
  - `app.css` (token values, `--accent-fill`); look at the terminal, the diff and the status chips in both themes with
    the Playwright MCP before opening the PR.
  - _Requirements: 7.1, 7.2_
- [ ] 8. Wording and small layout slips (`fix/copy-pass-2`)
  - Test first (Playwright): "1 line"; key notation in the welcome list and the File, explorer and terminal menus;
    "(stopped)" live and after reload; "Add folder".
  - `static/keys.js` (new), `index.html`, `app.js` (callers), `folders.js` (`addFolder`), `app.css`;
    `docs/usage.md` (Keyboard shortcuts), `docs/architecture.md`.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
