"""Specs: spec-driven development in Kiro's format. Requirements, then design, then tasks, each reviewed
before the next, then task-by-task implementation.

A spec is a folder:
  .codepilot/specs/<name>/requirements.md  user stories with EARS acceptance criteria (bugfix specs: bugfix.md)
                          design.md        architecture, interfaces, data, errors, testing, traced to requirements
                          tasks.md         "- [ ] 1. Title" / "- [x] 2.1 Sub-task" checklist; "_Requirements: 1.2_"
                                           lines tie tasks to acceptance criteria; "- [-]" is in progress
                          spec.json        codepilot's bookkeeping: kind and approved phase (Kiro ignores it)
Also listed, and workable: Kiro's .kiro/specs/<name>/ and GitHub Spec Kit's specs/<NNN-name>/
(spec.md, plan.md, tasks.md). Their phase is inferred from which files exist; codepilot keeps its own
state for them in .codepilot/specs/.state/.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

PHASES = ("requirements", "design", "tasks", "implement")
KINDS = ("feature", "bugfix")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
TASK_LINE = re.compile(r"^(\s*)- \[([ xX-])\]\s+(?:(\d+(?:\.\d+)*)\.?\s+)?(.*\S)\s*$")
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


@dataclass
class Spec:
    name: str
    folder: Path
    source: str  # codepilot | kiro | speckit
    kind: str = "feature"
    approved: str = ""  # the last approved phase
    tasks: list[Task] = field(default_factory=list)

    def doc(self, phase: str) -> Path:
        if self.source == "speckit":
            return self.folder / {"requirements": "spec.md", "design": "plan.md", "tasks": "tasks.md"}[phase]
        if phase == "requirements" and self.kind == "bugfix":
            return self.folder / "bugfix.md"
        return self.folder / f"{phase}.md"

    @property
    def phase(self) -> str:
        """The phase being worked on: the one after the last approved, or inferred from the files."""
        if self.approved in PHASES:
            return PHASES[min(PHASES.index(self.approved) + 1, len(PHASES) - 1)]
        if self.source == "codepilot":
            return "requirements"
        for phase in ("tasks", "design", "requirements"):
            if self.doc(phase).is_file():
                return "implement" if phase == "tasks" else PHASES[PHASES.index(phase) + 1]
        return "requirements"

    def info(self, root: Path) -> dict:
        done = sum(t.status == "done" for t in self.tasks)
        return {"name": self.name, "source": self.source, "kind": self.kind, "phase": self.phase,
                "approved": self.approved, "folder": str(self.folder.relative_to(root)),
                "docs": {p: str(self.doc(p).relative_to(root)) for p in PHASES[:3] if self.doc(p).is_file()},
                "doc_paths": {p: str(self.doc(p).relative_to(root)) for p in PHASES[:3]},
                "tasks": [t.__dict__ for t in self.tasks], "progress": [done, len(self.tasks)],
                "complete": bool(self.tasks) and done == len(self.tasks)}


def parse_tasks(text: str) -> list[Task]:
    tasks: list[Task] = []
    lines = text.splitlines()
    counters: list[int] = []
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
        if not tid:  # unnumbered checklist: number by position
            counters = counters[:depth + 1] + [0] * max(0, depth + 1 - len(counters))
            counters[depth] += 1
            tid = ".".join(str(c) for c in counters[:depth + 1])
        status = {"x": "done", "X": "done", "-": "in_progress"}.get(m.group(2), "todo")
        tasks.append(Task(id=tid, title=m.group(4), status=status, line=i, depth=depth))
    return tasks


def set_task_status(path: Path, task_id: str, status: str) -> Task:
    text = path.read_text()
    tasks = parse_tasks(text)
    task = next((t for t in tasks if t.id == task_id.rstrip(".")), None)
    if task is None:
        raise KeyError(f"no task {task_id} in {path.name}; tasks are {', '.join(t.id for t in tasks)}")
    lines = text.splitlines(keepends=True)
    mark = {"done": "x", "in_progress": "-", "todo": " "}[status]
    lines[task.line] = re.sub(r"- \[[ xX-]\]", f"- [{mark}]", lines[task.line], count=1)
    path.write_text("".join(lines))
    task.status = status
    return task


def _state_file(root: Path, source: str, name: str, folder: Path) -> Path:
    if source == "codepilot":
        return folder / "spec.json"
    return root / ".codepilot/specs/.state" / f"{source}__{name}.json"


def _load(root: Path, folder: Path, source: str) -> Spec:
    name = folder.name
    state: dict = {}
    try:
        state = json.loads(_state_file(root, source, name, folder).read_text())
    except (OSError, ValueError):
        pass
    kind = state.get("kind") or ("bugfix" if (folder / "bugfix.md").is_file() else "feature")
    spec = Spec(name=name, folder=folder, source=source, kind=kind, approved=state.get("approved", ""))
    tasks = spec.doc("tasks")
    if tasks.is_file():
        spec.tasks = parse_tasks(tasks.read_text(errors="replace"))
    return spec


def discover(root: Path) -> list[Spec]:
    found: dict[str, Spec] = {}
    sources = ((root / "specs", "speckit"), (root / ".kiro/specs", "kiro"), (root / ".codepilot/specs", "codepilot"))
    for base, source in sources:
        if not base.is_dir():
            continue
        for folder in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
            if source == "speckit" and not (folder / "spec.md").is_file():
                continue
            found[folder.name] = _load(root, folder, source)  # a codepilot spec wins a name clash
    return sorted(found.values(), key=lambda s: s.name)


def get(root: Path, name: str) -> Spec | None:
    return next((s for s in discover(root) if s.name == name), None)


def create(root: Path, name: str, kind: str = "feature") -> Spec:
    if not NAME.match(name):
        raise ValueError("Use lowercase letters, digits and dashes for the spec name (e.g. csv-export).")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    folder = root / ".codepilot/specs" / name
    if folder.exists() or get(root, name):
        raise FileExistsError(f"A spec named {name} already exists.")
    folder.mkdir(parents=True)
    (folder / "spec.json").write_text(json.dumps({"kind": kind, "approved": "", "created": time.time()}, indent=1))
    return _load(root, folder, "codepilot")


def approve(root: Path, spec: Spec, phase: str) -> Spec:
    """Approve a phase's document, moving the spec on to the next phase."""
    if phase not in PHASES[:3]:
        raise ValueError("Approve requirements, design or tasks.")
    if PHASES.index(phase) > PHASES.index(spec.phase):
        raise ValueError(f"Approve {spec.phase} first.")
    if not spec.doc(phase).is_file():
        raise FileNotFoundError(f"{spec.doc(phase).name} hasn't been written yet.")
    path = _state_file(root, spec.source, spec.name, spec.folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {"kind": spec.kind}
    current = state.get("approved") or spec.approved
    # Approving again (after editing an earlier document) never moves the spec backwards.
    if not current or PHASES.index(phase) > PHASES.index(current):
        state["approved"] = phase
    path.write_text(json.dumps(state, indent=1))
    return _load(root, spec.folder, spec.source)


def slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"a", "an", "the", "to", "for", "of", "and", "with", "in", "on", "i", "we", "want", "add", "make"}
    keep = [w for w in words if w not in stop][:5] or words[:5] or ["spec"]
    return "-".join(keep)[:60].strip("-")


# -- what the model is told, per phase -------------------------------------------------------------

PHASE_INSTRUCTIONS = {
    "requirements": (
        "Phase 1 of 3, REQUIREMENTS. Investigate read-only first (explore, read_file, search_code). Then write the "
        "document with write_spec(doc='requirements'): a short introduction, then numbered requirements, each "
        "with a user story ('As a <role>, I want <capability>, so that <benefit>') and numbered acceptance "
        "criteria in EARS form, e.g. '1.1 WHEN <event> THEN the <system> SHALL <response>', 'IF <condition> "
        "THEN the <system> SHALL <response>', 'WHILE <state> the <system> SHALL …'. Cover errors and edge cases. "
        "Ask at most three clarifying questions, only if essential. Don't design or write code yet. Finish by "
        "asking the user to review it and approve it in the Spec tab (or tell you what to change)."),
    "bugfix": (
        "Phase 1 of 3, BUGFIX ANALYSIS. Reproduce and investigate first (read code, traces, tests; a scratch "
        "reproduction with write_scratch + run_command if useful). Then write the document with "
        "write_spec(doc='requirements') with sections: Current behaviour (with exact reproduction steps or the "
        "failing case), Expected behaviour (EARS criteria: 'WHEN … THEN the system SHALL …'), Root cause "
        "(confirmed, or clearly marked as a hypothesis with evidence), and Unchanged behaviour (what must keep "
        "working: the regression criteria). Don't fix anything yet. Ask the user to review and approve it."),
    "design": (
        "Phase 2 of 3, DESIGN. Requirements are approved (below). Write the design with write_spec(doc='design'): "
        "Overview; Architecture (components and how they interact, naming the real files and modules); "
        "Components and interfaces (signatures); Data models; Error handling; Testing strategy (which tests prove "
        "which criteria). Trace each part to requirement numbers, and note alternatives you rejected and why. "
        "Don't write code yet. Ask the user to review and approve it."),
    "tasks": (
        "Phase 3 of 3, TASKS. Write the implementation plan with write_spec(doc='tasks'): an ordered checklist of "
        "small coding tasks (each about one commit), test-first where practical, as '- [ ] 1. Title' with "
        "sub-tasks '  - [ ] 1.1 Title'. Under each task, one to three indented bullets of specifics (files, "
        "functions) and a line '  - _Requirements: 1.1, 2.3_'. Only coding and testing tasks: no deployment, "
        "manual testing or meetings. Every acceptance criterion should be covered by some task. Ask the user "
        "to review and approve it."),
    "implement": (
        "IMPLEMENTATION. Work only on the task the user names, following design.md. Call "
        "update_task(task, 'in_progress') when you start. Write or update the tests for its acceptance criteria "
        "first, then the code, then run the tests. When the criteria are verified, call update_task(task, 'done') "
        "and stop: report what changed and how you verified it. Don't start the next task; the user does that. "
        "If the design turns out wrong, say so and propose a change to the spec with write_spec instead of "
        "drifting from it."),
}


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
    key = "bugfix" if phase == "requirements" and spec.kind == "bugfix" else phase
    earlier = PHASES[:PHASES.index(phase)] if phase != "implement" else PHASES[:3]
    docs = context_block(root, spec, tuple(p for p in earlier if p != "implement"))
    head = (f'<spec name="{spec.name}" kind="{spec.kind}" phase="{phase}" folder="{spec.folder.relative_to(root)}">\n'
            f"SPEC MODE. {PHASE_INSTRUCTIONS[key]}")
    return head + (f"\n\nSpec documents so far:\n{docs}" if docs else "") + "\n</spec>"
