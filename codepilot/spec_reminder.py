"""Reminding the agent of its task during a long implementation turn, which measurably reduces drift.

The reminder is a block inside the latest tool result. The system prompt stays frozen for caching, and a text block
beside the result would read as the user speaking to compaction, turn costs and the transcript.
"""

from __future__ import annotations

import re

from .specs import Spec, Task

EVERY = 6
MAX_CHARS = 1000
OPEN = "<spec_reminder "
CRITERION = re.compile(r"^\s*(?:[-*]\s+)?\**(\d+(?:\.\d+)+)\.?\**\.?\s+(\S.*)$")


def due(step: int) -> bool:
    return step % EVERY == 0


def criteria(requirements_md: str, ids: list[str]) -> dict[str, str]:
    """The text of each criterion by number. Criteria often wrap, so one runs to a blank line or a heading."""
    found: dict[str, str] = {}
    current = None
    for line in requirements_md.splitlines():
        m = CRITERION.match(line)
        if m:
            current = m.group(1) if m.group(1) in ids else None
            if current:
                found[current] = m.group(2).strip()
        elif not line.strip() or line.lstrip().startswith("#"):
            current = None
        elif current:
            found[current] += " " + line.strip()
    return found


def current(spec: Spec) -> Task | None:
    """The task in progress, and of a parent and its sub-task, the sub-task: it comes later in the file."""
    return next((t for t in reversed(spec.tasks) if t.status == "in_progress"), None)


def text(spec: Spec) -> str | None:
    task = current(spec)
    if task is None:
        return None
    doc = spec.doc("requirements")
    found = criteria(doc.read_text(errors="replace"), task.requirements) if doc.is_file() else {}
    body = f"Current task {task.id}: {task.title}."
    if found:
        body += " Criteria it must satisfy:\n" + "\n".join(f"{i} {found[i]}" for i in task.requirements if i in found)
    head, tail = f'{OPEN}spec="{spec.name}" task="{task.id}">', "\nStay on this task; don't start the next one.</spec_reminder>"
    room = MAX_CHARS - len(head) - len(tail)
    return head + (body if len(body) <= room else body[:room - 1] + "…") + tail
