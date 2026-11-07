# Design

## Where it lives

Front end only: every fact the card needs already reaches the page as events (`tool_call`, `tool_result`, `proposal`,
`plan`, `spec`, `verification`, `done`), live and in `history_events` on reload. So the same code draws both (1.4).
- `static/steps.js` (new): `stepText(name, input)`, a table of phrasings per tool (fallback "Used <tool>"), and
  `groupReads(rows)`. `app.js`'s `toolEl` calls it. The raw name and JSON move into the row's expanded part.
- `static/taskcard.js` (new): the plan card and the spec-run card, filing steps under an item. `plan.js` keeps the
  lifecycle (#61); its pinned view becomes the one-line header (2.4).
- No server or tool changes. `steps.js` reads tool names; a tool without a phrasing still gets a row.

## Readable steps (1)

- Phrasing by tool: `read_file` "Read <path>" (and the line range), `search_code` "Searched for <pattern>",
  `run_tests` "Ran the tests", `run_command` "Ran <first line of the command>", `update_plan` "Updated the plan · n of m",
  `write_spec` "Wrote <doc>.md", `explore` "Explored: <task>", web tools "Fetched <host>", and so on.
- A `propose_edit` row and its `proposal` card become one: the proposal row takes the tool row's place (1.2).
  The spec chip after `write_spec` goes; the row says it.
- Read-only steps (`read_file`, `list_files`, `search_code`, read-only `git`, trace tools, `recall`) in a row, with no
  other row between them, fold into one summary row once a second arrives (1.3). Errors never fold.

## The task card (2, 3)

- A plan card appears where the plan starts. Its items are rows: ○ to do, spinner while the turn runs and the item is
  "doing", ✓ done, ✗ failed (2.1, 2.2). The steps of the turn are filed under the item that was "doing" when they
  arrived; steps before any item is "doing" go under "Before the plan" (2.2, 2.3).
- A spec run ("Run all remaining", one turn per task) gets one card: one row per task, whose steps are its turn, with
  the receipt line from `verify.js` under it (3.1–3.3). The row links to the Spec tab (3.4).
- The pinned plan shows only its header line; a click scrolls to the card and opens the running item (2.4).

## Decisions to confirm

- The plan's checklist moves from the pinned bar into the card (pinned: one line). The alternative, both full, says it
  twice.
- Steps before the first "doing" item get their own "Before the plan" group rather than being dropped.
