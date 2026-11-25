"""Specs: spec-driven development in Kiro's format. Requirements, then design, then tasks, each reviewed
before the next, then task-by-task implementation.

A spec is a folder:
  .codepilot/specs/<name>/requirements.md  user stories with EARS acceptance criteria (bugfix specs: bugfix.md)
                          design.md        architecture, interfaces, data, errors, testing, traced to requirements
                          tasks.md         "- [ ] 1. Title" / "- [x] 2.1 Sub-task" checklist; "_Requirements: 1.2_"
                                           lines tie tasks to acceptance criteria; "- [-]" is in progress
                          spec.json        codepilot's bookkeeping: kind, profile and approved phase (Kiro ignores it)
Only .codepilot/specs/ is listed. Other tools' spec folders (.kiro/specs/, Spec Kit's specs/) belong to those
tools and aren't shown, even though the files share Kiro's format.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import spec_profiles, task_tree
from .spec_profiles import PHASES, PROFILES

KINDS = ("feature", "bugfix")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
# "- [ ] 1.1 Title", and the other ways a number gets written: "1.1.", "1.1:", "1.1)", "**1.1**", "Task 1.1:", "1.1 - "
TASK_LINE = re.compile(r"^(\s*)- \[([ xX-])\]\s+"
                       r"(?:(?:\*\*)?(?:task\s+)?(\d+(?:\.\d+)*)\.?(?:\*\*)?[:)]?(?:\s+[-\u2013\u2014])?\s+)?"
                       r"(.*\S)\s*$", re.I)
REQ_REF = re.compile(r"_?Requirements?:\s*([\d.,\s]+)_?", re.I)
MAX_DOC_CHARS = 30_000


@dataclass
class Task:
    id: str
    title: str
    status: str  # todo | in_progress | done
    line: int
    depth: int
    requirements: list[str] = field(default_factory=list)
    detail: str = ""
    parent: str = ""  # the task it's a sub-task of (task_tree.py)


@dataclass
class Spec:
    name: str
    folder: Path
    kind: str = "feature"
    approved: str = ""  # the last approved phase
    profile: str = "full"  # how much review it gets: spec_profiles.py
    tasks: list[Task] = field(default_factory=list)

    def doc(self, phase: str) -> Path:
        if phase == "requirements" and self.kind == "bugfix":
            return self.folder / "bugfix.md"
        return self.folder / f"{phase}.md"

    @property
    def phase(self) -> str:
        """The phase being worked on: the one after the last approved."""
        if self.approved in PHASES:
            return PHASES[min(PHASES.index(self.approved) + 1, len(PHASES) - 1)]
        return "requirements"

    def info(self, root: Path) -> dict:
        worked = task_tree.leaves(self.tasks)  # a parent is a heading for its sub-tasks: they're what's counted
        done = sum(t.status == "done" for t in worked)
        return {"name": self.name, "kind": self.kind, "profile": self.profile, "phase": self.phase,
                "approved": self.approved, "folder": str(self.folder.relative_to(root)),
                "docs": {p: str(self.doc(p).relative_to(root)) for p in PHASES[:3] if self.doc(p).is_file()},
                "doc_paths": {p: str(self.doc(p).relative_to(root)) for p in PHASES[:3]},
                "tasks": [t.__dict__ for t in self.tasks], "progress": [done, len(worked)],
                "complete": bool(worked) and done == len(worked)}


def parse_tasks(text: str) -> list[Task]:
    tasks: list[Task] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = TASK_LINE.match(line)
        if not m:
            if tasks and line.strip() and (line.startswith((" ", "\t")) or line.lstrip().startswith("_")):
                tasks[-1].detail += line.strip() + "\n"
                ref = REQ_REF.search(line)
                if ref:
                    tasks[-1].requirements += [r.strip() for r in ref.group(1).split(",") if r.strip()]
            continue
        depth = len(m.group(1).replace("\t", "  ")) // 2
        tid = m.group(3)
        parent = task_tree.parent_of(tasks, tid or "", depth)
        if not tid:  # unnumbered: numbered by position, under its parent
            tid = task_tree.next_number(tasks, parent)
        status = {"x": "done", "X": "done", "-": "in_progress"}.get(m.group(2), "todo")
        tasks.append(Task(id=tid, title=m.group(4), status=status, line=i, depth=depth, parent=parent))
    return tasks


def set_task_status(path: Path, task_id: str, status: str) -> Task:
    text = path.read_text()
    tasks = parse_tasks(text)
    task = next((t for t in tasks if t.id == task_id.rstrip(".")), None)
    if task is None:
        raise KeyError(f"no task {task_id} in {path.name}; tasks are {', '.join(t.id for t in tasks)}")
    lines = text.splitlines(keepends=True)
    task.status = status
    _mark(lines, task)
    for heading in task_tree.ancestors(tasks, task.id):  # each heading above follows its sub-tasks, nearest first
        heading.status = task_tree.rolled_up(tasks, heading.id)
        _mark(lines, heading)
    path.write_text("".join(lines))
    return task


def _mark(lines: list[str], task: Task) -> None:
    mark = {"done": "x", "in_progress": "-", "todo": " "}[task.status]
    lines[task.line] = re.sub(r"- \[[ xX-]\]", f"- [{mark}]", lines[task.line], count=1)


def set_task_tests(path: Path, task_id: str, text: str) -> None:
    """Write `text` (e.g. "_Tests: tests/test_x.py_") under the task, after its details, replacing an earlier one."""
    path.write_text(_with_tests(path.read_text(), task_id, text))


def _with_tests(doc: str, task_id: str, text: str) -> str:
    lines = doc.splitlines(keepends=True)
    task = next(t for t in parse_tasks(doc) if t.id == task_id.rstrip("."))
    indent = "  " * (task.depth + 1)
    end = task.line  # the task's last detail line: indented or "_…_", up to the next task
    for i in range(task.line + 1, len(lines)):
        if TASK_LINE.match(lines[i]) or (lines[i].strip() and not lines[i].startswith((" ", "\t", "_"))):
            break
        if lines[i].strip():
            if lines[i].strip().removeprefix("- ").startswith("_Tests:"):
                lines[i] = f"{indent}- {text}\n"
                return "".join(lines)
            end = i
    if not lines[end].endswith("\n"):
        lines[end] += "\n"
    lines.insert(end + 1, f"{indent}- {text}\n")
    return "".join(lines)


def _tests_line(task: Task) -> str:
    details = (d.removeprefix("- ") for d in task.detail.splitlines())
    return next((d for d in details if d.startswith("_Tests:")), "")


def keep_progress(old: str, new: str) -> tuple[str, list[str]]:
    """A rewrite of tasks.md during implementation, with the progress so far kept: a task that keeps its number keeps
    its checkbox and `_Tests_` line, a new task starts open, and headings follow their sub-tasks. Checkboxes change
    only through update_task, which runs a task's tests. Returns the text and the tasks whose checkbox it put back."""
    before = {t.id: t for t in parse_tasks(old)}
    lines = new.splitlines(keepends=True)
    tasks = parse_tasks(new)
    put_back = []
    for task in task_tree.leaves(tasks):
        was = before.get(task.id)
        status = was.status if was else "todo"
        if status != task.status:
            put_back.append(task.id)
            task.status = status
            _mark(lines, task)
    for heading in reversed([t for t in tasks if task_tree.children(tasks, t.id)]):  # deepest first
        heading.status = task_tree.rolled_up(tasks, heading.id)
        _mark(lines, heading)
    text = "".join(lines)
    for task in parse_tasks(text):
        kept = _tests_line(before[task.id]) if task.id in before else ""
        if kept and not _tests_line(task):
            text = _with_tests(text, task.id, kept)
    return text, put_back


def _load(folder: Path) -> Spec:
    state: dict = {}
    try:
        state = json.loads((folder / "spec.json").read_text())
    except (OSError, ValueError):
        pass
    kind = state.get("kind") or ("bugfix" if (folder / "bugfix.md").is_file() else "feature")
    profile = state.get("profile") if state.get("profile") in PROFILES else "full"
    spec = Spec(name=folder.name, folder=folder, kind=kind, approved=state.get("approved", ""), profile=profile)
    tasks = spec.doc("tasks")
    if tasks.is_file():
        spec.tasks = parse_tasks(tasks.read_text(errors="replace"))
    return spec


def discover(root: Path) -> list[Spec]:
    base = root / ".codepilot/specs"
    if not base.is_dir():
        return []
    return [_load(folder) for folder in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))]


def get(root: Path, name: str) -> Spec | None:
    return next((s for s in discover(root) if s.name == name), None)


def create(root: Path, name: str, kind: str = "feature", profile: str = "full") -> Spec:
    if not NAME.match(name):
        raise ValueError("Use lowercase letters, digits and dashes for the spec name (e.g. csv-export).")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}")
    folder = root / ".codepilot/specs" / name
    if folder.exists() or get(root, name):
        raise FileExistsError(f"A spec named {name} already exists.")
    folder.mkdir(parents=True)
    state = {"kind": kind, "approved": "", "created": time.time()} | ({"profile": profile} if profile != "full" else {})
    (folder / "spec.json").write_text(json.dumps(state, indent=1))
    return _load(folder)


def _state(spec: Spec) -> dict:
    try:
        return json.loads((spec.folder / "spec.json").read_text())
    except (OSError, ValueError):
        return {"kind": spec.kind}


def approve(root: Path, spec: Spec, phase: str) -> Spec:
    """Approve a phase's document, moving the spec on to the next phase."""
    if phase not in PHASES[:3]:
        raise ValueError("Approve requirements, design or tasks.")
    present = {doc for doc in PHASES[:3] if spec.doc(doc).is_file()}
    refused = spec_profiles.may_approve(spec.profile, spec.phase, phase, present)
    if refused:
        raise ValueError(refused)
    path = spec.folder / "spec.json"
    state = _state(spec)
    current = state.get("approved") or spec.approved
    # Approving again (after editing an earlier document) never moves the spec backwards.
    if not current or PHASES.index(phase) > PHASES.index(current):
        state["approved"] = phase
    path.write_text(json.dumps(state, indent=1))
    return _load(spec.folder)


def set_profile(root: Path, spec: Spec, profile: str) -> Spec:
    """Move a quick spec to full review, keeping its documents. Past planning there's nothing left to review."""
    if profile != "full":
        raise ValueError("A spec can only switch to full review.")
    if not spec_profiles.can_switch_to_full(spec.approved):
        raise ValueError("Already approved; it's past planning.")
    (spec.folder / "spec.json").write_text(json.dumps({**_state(spec), "profile": profile}, indent=1))
    return _load(spec.folder)


def slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"a", "an", "the", "to", "for", "of", "and", "with", "in", "on", "i", "we", "want", "add", "make"}
    keep = [w for w in words if w not in stop][:5] or words[:5] or ["spec"]
    return "-".join(keep)[:60].strip("-")


def context_block(root: Path, spec: Spec, phases: tuple[str, ...]) -> str:
    """The spec documents to attach for this turn, so they survive compaction."""
    parts = []
    for phase in phases:
        path = spec.doc(phase)
        if path.is_file():
            text = path.read_text(errors="replace")
            if len(text) > MAX_DOC_CHARS:
                text = text[:MAX_DOC_CHARS] + "\n[... truncated ...]"
            parts.append(f"### {path.relative_to(root)}\n{text}")
    return "\n\n".join(parts)


def turn_text(root: Path, spec: Spec) -> str:
    phase = spec.phase
    quick = spec.profile == "quick"
    docs = context_block(root, spec, PHASES[:3] if quick or phase == "implement" else PHASES[:PHASES.index(phase)])
    profile = ' profile="quick"' if quick else ""
    head = (f'<spec name="{spec.name}" kind="{spec.kind}" phase="{phase}"{profile} '
            f'folder="{spec.folder.relative_to(root)}">\n'
            f"SPEC MODE. {spec_profiles.instructions(spec.profile, spec.kind, phase)}")
    return head + (f"\n\nSpec documents so far:\n{docs}" if docs else "") + "\n</spec>"
