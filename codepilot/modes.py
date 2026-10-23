"""Modes: focused agent profiles (Ask, Plan, Build, Debug, Bug-hunt, Review, plus your own).

A mode is just configuration for the same Bedrock loop: extra instructions, skills preloaded into the system
prompt, tools that are switched off, and optionally a model tier. That is all "agents" in most agentic IDEs
are. Custom modes are Markdown files with front matter in ~/.codepilot/modes/ or <workspace>/.codepilot/modes/:

    ---
    name: perf
    label: Perf
    description: Find and fix performance problems
    tier: hard                    # optional: fast | main | hard
    blocked: run_command          # optional, comma-separated tool names
    skills: diagnose-bug          # optional, comma-separated skills to preload
    ---
    Instructions for this mode...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import skills as skills_mod

READ_ONLY_BLOCK = {"propose_edit", "write_scratch", "run_command", "run_tests", "run_checks"}


@dataclass
class Mode:
    name: str
    label: str
    description: str
    instructions: str
    blocked: set[str] = field(default_factory=set)
    skills: list[str] = field(default_factory=list)
    tier: str | None = None
    builtin: bool = True

    def public(self) -> dict:
        return {"name": self.name, "label": self.label, "description": self.description, "tier": self.tier,
                "blocked": sorted(self.blocked), "builtin": self.builtin}


BUILTIN = [
    Mode("ask", "Ask", "Questions and explanations. Read-only; runs nothing.",
         "ASK MODE: answer questions about the code and explain how things work. Read and search as needed, "
         "but don't run commands or propose changes. Be direct and cite path:line.",
         blocked=set(READ_ONLY_BLOCK)),
    Mode("plan", "Plan", "Investigate read-only and produce an agreed plan before any change.",
         "PLAN MODE: the user wants a plan before any change. Investigate read-only, then present a concrete "
         "step-by-step plan (files, functions, tests, risks, verification) and keep it in update_plan. Edits "
         "and commands are disabled; the user switches to Build to carry it out.",
         blocked={"propose_edit", "write_scratch", "run_command"}, skills=["plan-feature"]),
    Mode("build", "Build", "Implement features and changes end to end, verified by tests.",
         "BUILD MODE: implement the request end to end in small verified steps: understand the code, keep a "
         "checklist with update_plan for anything over two steps, propose minimal edits in the local style, and "
         "after the user applies them run the relevant tests and checks (run_checks) and fix what they find. "
         "Add or update tests for new behaviour (see the tdd skill)."),
    Mode("debug", "Debug", "Find the root cause of a specific bug and fix it with a regression test.",
         "DEBUG MODE: follow the diagnose-bug workflow below strictly. Build a reproduction before proposing any "
         "fix (unless the user insists), test hypotheses one at a time, and finish with a regression test and a "
         "re-run of the reproduction.",
         skills=["diagnose-bug"]),
    Mode("bughunt", "Bug-hunt", "Proactively search the codebase for real, verified bugs. Reports, doesn't edit.",
         "BUG-HUNT MODE: there is no bug report; your job is to find real defects. Work like this:\n"
         "1. Prioritise risky areas: recently and frequently changed files (git log), complex functions in the "
         "repository map, error handling, boundaries (parsing, I/O, network, concurrency, time zones, money), "
         "and anything the deterministic checks flag (run_checks first).\n"
         "2. Investigate areas in parallel with several explore calls in one turn, each with a focused brief.\n"
         "3. For every suspected bug, try to confirm it: a scratch script or a test that demonstrates the wrong "
         "behaviour (write_scratch + run_command, or run_tests). Mark each finding confirmed or suspected.\n"
         "4. Report findings ranked by severity: path:line, the triggering input or scenario, the evidence, and "
         "the fix. No style nits. Don't propose edits; the user switches to Debug or Build to fix.",
         blocked={"propose_edit"}),
    Mode("review", "Review", "Review changes or code against intent and the repo's standards.",
         "REVIEW MODE: follow the code-review workflow below. Use run_checks for deterministic findings and "
         "verify suspected defects before reporting them. Don't propose edits unless the user asks.",
         blocked={"propose_edit"}, skills=["code-review"]),
]
ALIASES = {"act": "build", "develop": "build", "bug-hunt": "bughunt"}
DEFAULT = "build"
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _parse(path: Path) -> Mode | None:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    m = _FRONT.match(text)
    meta: dict[str, str] = {}
    body = text
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            k, sep, v = line.partition(":")
            if sep:
                meta[k.strip()] = v.split("#", 1)[0].strip().strip("\"'")
    name = (meta.get("name") or path.stem).lower()
    split = lambda v: [x.strip() for x in v.split(",") if x.strip()]  # noqa: E731
    tier = meta.get("tier") or None
    return Mode(name=name, label=meta.get("label") or name.title(), description=meta.get("description", ""),
                instructions=body.strip(), blocked=set(split(meta.get("blocked", ""))),
                skills=split(meta.get("skills", "")), tier=tier if tier in ("fast", "main", "hard") else None,
                builtin=False)


def all_modes(root: Path | None, home: Path) -> list[Mode]:
    modes = {m.name: m for m in BUILTIN}
    dirs = [home / "modes"] + ([root / ".codepilot" / "modes"] if root else [])
    for d in dirs:
        if d.is_dir():
            for f in sorted(d.glob("*.md")):
                mode = _parse(f)
                if mode:
                    modes[mode.name] = mode
    return list(modes.values())


def get(name: str | None, root: Path | None, home: Path) -> Mode:
    name = ALIASES.get((name or DEFAULT).lower(), (name or DEFAULT).lower())
    modes = {m.name: m for m in all_modes(root, home)}
    return modes.get(name) or modes[DEFAULT]


def system_text(mode: Mode, root: Path | None, home: Path) -> str:
    parts = [mode.instructions]
    if mode.blocked:
        parts.append("Disabled in this mode: " + ", ".join(sorted(mode.blocked)) + ".")
    for skill_name in mode.skills:
        skill = skills_mod.find(skill_name, root, home)
        if skill:
            parts.append(f'<skill name="{skill.name}">\n{skill.body}\n</skill>')
    return "\n\n".join(parts)
