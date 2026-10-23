"""Skills (Agent Skills / Claude Code SKILL.md format). Instruction files and steering: see steering.py.

A skill is a folder containing SKILL.md with YAML front matter (`name`, `description`) and a Markdown
body. Only names and descriptions go into the system prompt; the model calls `load_skill` to read
the body when a task calls for it, so unused skills cost almost nothing.

Search order (later wins on name clashes):
  1. skills bundled with codepilot
  2. ~/.codepilot/skills, ~/.agents/skills and ~/.kiro/skills
  3. extra dirs in CODEPILOT_SKILL_DIRS (comma-separated), e.g. ~/.claude/skills
  4. <workspace>/.agents/skills, <workspace>/.claude/skills and <workspace>/.codepilot/skills

Skills with `disable-model-invocation: true` are user-invoked only: they are hidden from the model's list
and run when the user types `/<name>` in chat.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

BUNDLED = Path(__file__).parent / "skills_bundled"



@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path
    user_only: bool = False


def _parse(path: Path) -> Skill | None:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    meta: dict[str, str] = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip()] = value.strip().strip("\"'")
    name = meta.get("name") or path.parent.name
    user_only = meta.get("disable-model-invocation", "").lower() == "true"
    return Skill(name=name, description=meta.get("description", "")[:400], body=body.strip(), path=path,
                 user_only=user_only)


def skill_dirs(root: Path | None, home: Path) -> list[Path]:
    dirs = [BUNDLED, home / "skills", Path.home() / ".agents" / "skills", Path.home() / ".kiro" / "skills"]
    dirs += [Path(d.strip()).expanduser() for d in os.environ.get("CODEPILOT_SKILL_DIRS", "").split(",") if d.strip()]
    if root is not None:
        dirs += [root / ".agents" / "skills", root / ".claude" / "skills", root / ".codepilot" / "skills"]
    return dirs


def discover(root: Path | None, home: Path) -> list[Skill]:
    found: dict[str, Skill] = {}
    for d in skill_dirs(root, home):
        if not d.is_dir():
            continue
        for skill_md in sorted([*d.glob("*/SKILL.md"), *d.glob("*/*/SKILL.md")]):
            skill = _parse(skill_md)
            if skill:
                found[skill.name] = skill
    return sorted(found.values(), key=lambda s: s.name)


SLASH = re.compile(r"^/([\w.-]+)(?:\s+(.*))?$", re.DOTALL)


def slash_command(text: str, root: Path | None, home: Path) -> tuple[Skill, str] | None:
    """`/name rest` -> (skill, rest) when name is a known skill."""
    m = SLASH.match(text.strip())
    if not m:
        return None
    skill = find(m.group(1), root, home)
    return (skill, (m.group(2) or "").strip()) if skill else None


def find(name: str, root: Path | None, home: Path) -> Skill | None:
    return next((s for s in discover(root, home) if s.name == name), None)


def project_instructions(root: Path | None, home: Path | None = None) -> str:
    """Always-on steering for a workspace (kept for older callers; see steering.py)."""
    from . import steering

    return steering.always_text(root, home or Path.home() / ".codepilot")
