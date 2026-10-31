"""How much ceremony a spec gets: what may be written and approved when, and what the model is told.

A full spec reviews each document in turn. A quick one is written in one turn and reviewed once, for changes that
deserve a plan but not three rounds of review. Both use the same phases, so nothing else has to know the difference.
This module knows nothing about files.
"""

from __future__ import annotations

import re

PROFILES = ("full", "quick")
PHASES = ("requirements", "design", "tasks", "implement")
DOCS = PHASES[:3]

# Specs longer than this get skimmed instead of reviewed. These are asked for, never enforced.
BUDGET = (" Keep it short enough to review properly: at most 5 acceptance criteria per requirement and about 150 lines "
          "per document. If it needs more, suggest splitting the spec.")

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

QUICK_START = ("QUICK SPEC: one review, so write the whole plan in this turn. Investigate read-only first, briefly "
               "(explore, read_file, search_code). Then call write_spec three times. ")
QUICK_REST = ("doc='design': the real files and modules involved, the interfaces, the errors, and which tests prove "
              "which criteria. doc='tasks': ordered coding tasks, test-first where practical, as '- [ ] 1. Title', each "
              "with one or two indented bullets and a line '  - _Requirements: 1.1_'. Keep to the budget: at most 3 "
              "requirements with at most 4 criteria each, a design of about 40 lines, at most 6 tasks. If it needs "
              "more, say so: it should be a full spec. Don't write code yet. Ask the user to review the plan and "
              "approve it in the Spec tab.")
QUICK_INSTRUCTIONS = {
    "feature": (QUICK_START + "doc='requirements': a short introduction, then numbered requirements, each a user story "
                "with EARS criteria, e.g. '1.1 WHEN <event> THEN the <system> SHALL <response>'. " + QUICK_REST),
    "bugfix": (QUICK_START + "doc='requirements': Current behaviour (with reproduction steps), Expected behaviour (EARS "
               "criteria numbered 1.1, 1.2), Root cause, and Unchanged behaviour. " + QUICK_REST),
}


def may_write(profile: str, phase: str, doc: str) -> bool:
    return profile == "quick" or PHASES.index(doc) <= PHASES.index(phase)


def may_approve(profile: str, phase: str, target: str, docs_present: set[str]) -> str | None:
    """None if `target` can be approved now, otherwise why not."""
    if profile == "quick":
        if target != "tasks":
            return "A quick spec is approved as one plan."
        return None if set(DOCS) <= docs_present else "Write the design and tasks first (or ask codepilot to finish the plan)."
    if PHASES.index(target) > PHASES.index(phase):
        return f"Approve {phase} first."
    return None if target in docs_present else f"The {target} document hasn't been written yet."


def can_switch_to_full(approved: str) -> bool:
    return not approved


def instructions(profile: str, kind: str, phase: str) -> str:
    if phase == "implement":
        return PHASE_INSTRUCTIONS[phase]
    if profile == "quick":
        return QUICK_INSTRUCTIONS.get(kind, QUICK_INSTRUCTIONS["feature"])  # spec.json is hand-editable
    key = "bugfix" if phase == "requirements" and kind == "bugfix" else phase
    return PHASE_INSTRUCTIONS[key] + BUDGET


def requested(text: str) -> tuple[str, str]:
    """(profile, description): "quick add x" asks for a quick spec of "add x"."""
    m = re.match(r"quick\s+(\S.*)", text.strip(), re.I | re.S)
    return ("quick", m.group(1)) if m else ("full", text)
