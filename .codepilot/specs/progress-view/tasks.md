# Tasks

- [x] 1. Cards in the Progress view, a marker in the chat
  - Test first (Playwright): a plan's card is in Progress with its work, and the chat has its marker; a reload draws
    the same; Edit removes a later card; another session shows its own; Apply on a filed change; existing plan and
    spec-run card tests point at the view.
  - `static/progress.js`; `taskcard.js`, `plan.js`, `specrun.js`, `app.js`, `steps.js`, `verify.js`, `cost.js` wiring.
  - _Requirements: 1.1, 2.1, 2.3_
  - _Tests: tests/e2e/test_progress_view_ui.py (card and line, reload, Edit, sessions, filed change), test_plan_ui.py, test_plan_card_ui.py, test_spec_run_card_ui.py_
- [x] 2. The view: badge, switching once, empty state, the links
  - Test first (Playwright): the badge counts while live; the sidebar switches once per card, not on reload; the
    marker's View progress and the pinned line open the view at the card; the empty state.
  - `static/progress.js`, `plan.js`; `index.html`, `app.css`; `docs/usage.md`, `docs/specs.md`, `docs/architecture.md`.
  - _Requirements: 1.2, 1.3, 1.4, 2.1, 2.2_
  - _Tests: tests/e2e/test_progress_view_ui.py (badge, switching once, links, empty state)_
