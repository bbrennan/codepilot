# Tasks

- [x] 1. Switcher in the chat title
  - Test first (Playwright): title opens the list, marked, newest first; search by title and folder; Enter, click,
    Escape; New session first.
  - `static/sessions.js`, `index.html`, `app.css`; `app.js` wiring.
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Tests: tests/e2e/test_session_switcher_ui.py (switcher, spinner)_
- [x] 2. Sessions sidebar: search, groups, shown first
  - Test first (Playwright): grouped by folder, newest group first, "No folder"; the search box filters; a first visit
    shows Sessions.
  - `static/sessions.js`; `app.js` default view; `docs/usage.md`.
  - _Requirements: 2.1, 2.2, 2.3_
  - _Tests: tests/e2e/test_session_switcher_ui.py (sidebar groups, search survives refresh, first visit)_
