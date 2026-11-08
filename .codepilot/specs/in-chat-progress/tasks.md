# Tasks

- [x] 1. Readable step rows
  - Test first (Playwright): every scripted tool shows a verb-and-object row; the tool name and JSON are behind a click;
    an unknown tool reads "Used <tool>"; a reload shows the same rows.
  - `static/steps.js` (`stepText`); `toolEl` uses it.
  - _Requirements: 1.1, 1.4_
- [x] 2. One row per change, no spec chips
  - Test first: "fix two things" shows two change rows and no `propose_edit` rows; a quick spec shows three "Wrote …"
    rows and no chips; both after a reload too.
  - _Requirements: 1.2, 1.4_
- [x] 3. Reads grouped
  - Test first: the scripted "long task" (seven reads) shows one "Read agent/core.py 7 times" row (files counted once each) that expands to seven; an error
    between reads splits the group.
  - `groupReads` in `steps.js`.
  - _Requirements: 1.3_
- [x] 4. The plan card
  - Test first: "plan slowly" shows a card; its "doing" item spins only while the turn runs; steps are filed under it
    and expand on click; the pinned plan is one line that scrolls to the card; the same after a reload.
  - `static/taskcard.js`; `plan.js` pins the header only.
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
- [x] 5. Spec runs as a task card
  - Test first: "Run all remaining" on a two-task spec shows a card with both tasks; each ends done (or paused, with the
    reason) and shows its receipt; a click expands its steps; the row opens the Spec tab.
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
- [x] 6. Docs and a real-browser check
  - `docs/usage.md` (talking to it, the plan, specs) and `docs/specs.md` (running tasks); screenshots, dark and light.
  - _Requirements: all_
