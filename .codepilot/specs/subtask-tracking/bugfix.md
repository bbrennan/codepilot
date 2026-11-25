# Bug analysis: sub-tasks aren't tracked

## Current behaviour

Spec mode works through a task list with sub-tasks (`1.1`, `1.2`) but loses track of what is done. With

```
- [ ] 1. Export pipeline
  - [ ] 1.1 Write the CSV writer
  - [ ] 1.2 Stream big reports
- [ ] 2. Button
```

1. Marking 1.1 and 1.2 done leaves 1 unticked. **Run next task** then runs task 1 again, for work already done.
2. Task 1 can be marked done while 1.1 and 1.2 are open, so the list shows them open and **Run all** runs them again.
3. **Run all remaining** queues 1, 1.1 and 1.2 as three turns: the parent's turn does (or half-does) its sub-tasks,
   and the run pauses ("task 1 isn't marked done") or repeats them.
4. A sub-task written `1.1: Title`, `1.1) Title`, `**1.1** Title` or `Task 1.1: Title` is read as a second task `1`:
   `update_task("1.1")` fails ("no task 1.1") and `update_task("1")` ticks the first line with that id, the parent.
5. A numbered parent with unnumbered sub-tasks numbers them `0.1`, `0.2`.

## Expected behaviour

1.1 WHEN the last open sub-task of a task is marked done THEN the system SHALL tick that task, and its parent in turn.
1.2 WHEN a sub-task is started or done while others are open THEN its parent SHALL show in progress (`[-]`).
1.3 IF a task with open sub-tasks is marked done THEN the system SHALL refuse, naming the open sub-tasks.
1.4 WHEN a sub-task is marked THEN the tool's result SHALL say what that did to its parent and which of its siblings
    are still open, so the model knows what is ticked.
2.1 The system SHALL read `1.1:`, `1.1)`, `**1.1**` and `Task 1.1:` as task `1.1`, with the title without that markup.
2.2 An unnumbered sub-task SHALL be numbered under its parent (`1.1` under `1.`).
2.3 IF two tasks have the same number THEN `update_task` SHALL refuse it, naming both lines, rather than tick one.
2.4 `update_task` SHALL accept `Task 1.1`, `1.1.` and `1.1 Title` as task `1.1`.
2.5 WHEN `write_spec` rewrites tasks.md during implementation THEN each task that keeps its number SHALL keep its
    checkbox and `_Tests_` line; checkboxes change only through `update_task`.
3.1 **Run next task** SHALL run the first open task with no open sub-tasks.
3.2 **Run all remaining**, and **Run** on a parent, SHALL run each open sub-task once and the parent not on its own.
3.3 The message for a sub-task SHALL name its parent task.
3.4 The progress count SHALL count the tasks that are worked on: sub-tasks, and tasks without any.

## Root cause

Confirmed by tracing the turn the model gets for "Implement task 1" (a parent of 1.1 and 1.2) and every result it gets
back. **codepilot gives the task hierarchy no meaning anywhere.** `parse_tasks` records each task's depth, but nothing
reads it. Every layer treats a parent and its sub-tasks as unrelated peers, so the model has to guess, and each layer
guesses differently:

- **The runner asks for a heading as work.** Run next picks the first open line (the parent), and Run all queues the
  parent and each sub-task as separate turns.
- **The instructions contradict themselves.** "Work only on the task the user names … don't start the next task": for
  task 1, doing 1.1 and 1.2 breaks the rule, and doing neither leaves nothing to do.
- **The tool accepts anything and says nothing back.** `update_task("1", "done")` ticks the parent over open sub-tasks.
  Ticking the last sub-task leaves the parent open. A result is just "Task 1.1 is now done", never where its parent
  stands. An unknown id gets a bare list of ids, without titles or structure.
- **The file has two writers.** In the implement phase, `write_spec(doc='tasks')` rewrites the whole file, checkboxes
  included, without the tests `update_task` requires. Nothing reconciles the two.
- **Ids are fragile.** Only `1.1` and `1.1.` are read as numbers. Other common forms become a second task `1`, so a
  correct `update_task("1.1")` fails and `update_task("1")` hits the first line with that id. `"Task 1.1"` passed as
  the argument fails too. Unnumbered sub-tasks under a numbered parent are numbered `0.1`.

## Unchanged behaviour

- A flat task list behaves exactly as before.
- Each sub-task still needs its tests (or a reason) to be done; a parent ticked by its sub-tasks needs none of its own.
- `tasks.md` stays Kiro's format, and editing it by hand still works.
