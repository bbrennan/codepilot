"""A spec's tasks as a tree: sub-tasks (1.1, 1.2) under their task (1).

A task with sub-tasks is a heading for them. Its checkbox follows theirs, so the list never shows a parent done with
work open under it, or open with all its work done. Only sub-tasks (and tasks without any) are worked on, one turn
each, and each needs its own tests to be done.
"""

from __future__ import annotations

import re
from typing import Protocol

_ID = re.compile(r"^\s*(?:task\s+)?(\d+(?:\.\d+)*)\.?(?:[:)]|\s|$)", re.I)


class Node(Protocol):  # specs.Task
    id: str
    title: str
    status: str
    depth: int
    parent: str


def parent_of(tasks: list, tid: str, depth: int) -> str:
    """By number when the task above it has the prefix (1.2 is under 1, even written flush left), else by indentation:
    the nearest task above that is indented less."""
    if "." in tid and any(t.id == tid.rsplit(".", 1)[0] for t in tasks):
        return tid.rsplit(".", 1)[0]
    return next((t.id for t in reversed(tasks) if t.depth < depth), "")


def next_number(tasks: list, parent: str) -> str:
    """The number of an unnumbered task: the one after its siblings', under its parent."""
    siblings = [t for t in tasks if t.parent == parent]
    last = siblings[-1].id.rsplit(".", 1)[-1] if siblings else "0"
    n = int(last) + 1 if last.isdigit() else len(siblings) + 1
    return f"{parent}.{n}" if parent else str(n)


def normalise(task: str) -> str:
    """The number in what the model passed: "Task 1.1", "1.1." and "1.1 Write it" are 1.1. Anything else as it is."""
    m = _ID.match(str(task))
    return m.group(1) if m else str(task).strip()


def children(tasks: list[Node], tid: str) -> list[Node]:
    return [t for t in tasks if t.parent == tid]


def leaves(tasks: list[Node]) -> list[Node]:
    """The tasks that are worked on: sub-tasks, and tasks without any."""
    parents = {t.parent for t in tasks}
    return [t for t in tasks if t.id not in parents]


def open_under(tasks: list[Node], tid: str) -> list[Node]:
    """The open leaves under a task, however deep."""
    found: list[Node] = []
    for child in children(tasks, tid):
        found += open_under(tasks, child.id) if children(tasks, child.id) else [child] * (child.status != "done")
    return found


def rolled_up(tasks: list[Node], tid: str) -> str:
    """A parent's status from its sub-tasks': done when all are, in progress once any is started, else todo."""
    statuses = {t.status for t in children(tasks, tid)}
    if statuses == {"done"}:
        return "done"
    return "in_progress" if statuses & {"done", "in_progress"} else "todo"


def ancestors(tasks: list[Node], tid: str) -> list[Node]:
    """The task's parent, its parent's parent, and so on: nearest first."""
    by_id = {t.id: t for t in tasks}
    found, seen = [], {tid}
    while (pid := by_id[tid].parent if tid in by_id else "") and pid in by_id and pid not in seen:
        found.append(by_id[pid])
        seen.add(pid)
        tid = pid
    return found


def duplicates(tasks: list[Node], tid: str) -> list[Node]:
    same = [t for t in tasks if t.id == tid]
    return same if len(same) > 1 else []


def refusal(tasks: list[Node], tid: str, status: str) -> str | None:
    """Why `update_task(tid, status)` can't go ahead: no such task, two with that number, or a heading's open work."""
    same = [t for t in tasks if t.id == tid]
    if not same:
        return f"no task {tid} in tasks.md; tasks are " + ", ".join(f"{t.id} ({t.title})" for t in tasks)
    if len(same) > 1:
        lines = ", ".join(f"line {t.line + 1} ({t.title})" for t in same)
        return (f"tasks.md numbers {len(same)} tasks {tid}: {lines}. Renumber them with write_spec, then mark the one "
                "you mean.")
    if not children(tasks, tid) or settled(tasks, tid, status):
        return None
    if status == "done":
        return refuse_done(tasks, tid)
    open_ = ", ".join(f"{t.id} ({t.title})" for t in open_under(tasks, tid)) or "none"
    return (f"Task {tid} ({same[0].title}) is a heading for its sub-tasks (open: {open_}). Work on and mark those "
            f"one at a time; task {tid} follows them.")


def settled(tasks: list[Node], tid: str, status: str) -> str | None:
    """Marking a heading done when its sub-tasks already ticked it: nothing to do, and not an error."""
    task = next((t for t in tasks if t.id == tid), None)
    if task is None or status != "done" or not children(tasks, tid) or open_under(tasks, tid):
        return None
    return f"Task {tid} ({task.title}) is already done: it ticked itself when its last sub-task was done."


def refuse_done(tasks: list[Node], tid: str) -> str | None:
    """Why a task can't be marked done yet: its sub-tasks are open. Each is done on its own, with its own tests."""
    left = open_under(tasks, tid)
    if not left:
        return None
    names = ", ".join(f"{t.id} ({t.title})" for t in left)
    return (f"Task {tid} has open sub-tasks: {names}. Mark each sub-task done when its tests pass; task {tid} is "
            "ticked when its last sub-task is.")


def note(tasks: list[Node], tid: str) -> str:
    """What marking a task did to its parent, and what's still open beside it, for the model to know where it stands."""
    by_id = {t.id: t for t in tasks}
    parent = by_id.get(by_id[tid].parent) if tid in by_id else None
    if parent is None:
        return ""
    left = open_under(tasks, parent.id)
    if not left:
        return f" Task {parent.id} ({parent.title}) is done too: all its sub-tasks are."
    return (f" Task {parent.id} ({parent.title}) is {parent.status.replace('_', ' ')}; still open under it: "
            + ", ".join(f"{t.id} ({t.title})" for t in left) + ".")
