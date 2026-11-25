# Design

## The rule

**A task with sub-tasks is a heading. Its sub-tasks are the work.** Each sub-task, like each task without any, is one
unit: one turn, its own tests, its own checkbox. A heading's checkbox is never set directly. It follows its sub-tasks:
done when all are done, in progress once any has started, open otherwise. Kiro uses the same rule, and its format is
the one codepilot follows. Each fix below applies this rule in one layer.

## Layers

| Layer | Today | With the rule |
|---|---|---|
| Model (`specs.py`, new `task_tree.py`) | flat list; depth unused | `Task.parent`; `task_tree`: `children`, `leaves`, `open_under`, `rolled_up`, `ancestors` |
| Parser (`specs.parse_tasks`) | `1.1`/`1.1.` only; counters ignore numbered parents | the forms in 2.1; unnumbered tasks numbered under their parent (2.2) |
| Writer (`specs.set_task_status`) | edits one line | edits the line, then re-derives each ancestor's checkbox (1.1, 1.2) |
| Tool (`update_task` in `tools.py`, logic in `task_tree`) | accepts any id and status | refuses done on a heading with open sub-tasks (1.3) or a duplicate id (2.3); normalises the id (2.4); the result says where the parent stands (1.4) |
| Second writer (`write_spec`, tasks, implement phase) | overwrites checkboxes | `specs.keep_progress(old, new)` carries checkboxes and `_Tests_` over by task number (2.5) |
| Runner (`static/specrun.js`) | every open line | `openLeaves(spec, under)`; Run on a heading runs its open sub-tasks; the message names the parent (3.1–3.3) |
| Progress (`Spec.info`, `app.js` bar) | counts headings and their sub-tasks | counts leaves (3.4) |
| Instructions (`spec_profiles.py` implement) | silent on sub-tasks | one sentence: work and mark sub-tasks one by one; a heading ticks itself |

## Decisions

- **Refuse, don't cascade.** Marking a heading done doesn't tick its sub-tasks. That would tick work without its tests,
  and the granular tracking is the point.
- **Derive on write, read the file as it is.** A parent ticked by hand still reads as ticked. The roll-up runs when
  codepilot changes a status, and the runner and progress go by leaves, so a stale heading can't send work twice.
- **Parent by number, else by indentation.** `1.2` is under `1` even when written flush left. An unnumbered task goes
  under the nearest task above that is indented less.
- **Rejected: one turn per heading** (the model does all of 1.x and ticks each). Fewer turns, but a long turn drifts,
  and a failing 1.2 would leave the whole heading's turn unfinished. Per-sub-task turns match how tests gate "done".

## Tests

- Unit, `tests/test_task_tree.py`: parent, leaves, roll-up two levels deep, refusal and note texts.
- Unit, `tests/test_specs.py`: each id form; numbering under a parent; roll-up on disk (ticks, then back to `[-]`);
  progress counts leaves; `keep_progress`.
- Unit, `tests/test_task_tests.py`: the `update_task` refusals and the note in its result; `write_spec` keeping
  checkboxes.
- E2E, `tests/e2e/test_spec_run_card_ui.py`: Run all on a spec with sub-tasks sends 1.1, 1.2, 2 (each naming its
  parent) and the card lists those; Run next runs 1.1; Run on heading 1 runs 1.1 and 1.2.
