# Tasks

- [x] 1. Done runs the task's tests
  - Test first (unit): the cases in design.md "Tests"; then `task_tests.py`, `specs.set_task_tests`, `update_task`
    wiring and the implement instructions.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1_
- [x] 2. Asking first
  - Test first (unit): approval asks for a done with tests unless auto-run; the approval shows the command; it's
    guarded after external content. Then `asks`, `describe`, `requires_approval`, `approval_policy`.
  - _Requirements: 2.1, 2.2_
- [x] 3. On the card, and the docs
  - Test first (Playwright): a spec run's task shows "✓ 1 test passes", and a task done without tests shows its reason.
  - `static/specrun.js`; `docs/specs.md`.
  - _Requirements: 3.2_
