"""Steering: standing instructions codepilot follows, in Kiro's format so the same files work in both.

Where (a workspace doc overrides a global one with the same name):
  ~/.codepilot/steering/*.md                every workspace
  <workspace>/.codepilot/steering/*.md      this workspace; commit it to share with your team

Also read, so a repo set up for another assistant behaves the same here:
  ~/.codepilot/AGENTS.md, ~/.kiro/steering/*.md
  AGENTS.md, CLAUDE.md, CODEPILOT.md, .cursorrules, .windsurfrules, .github/copilot-instructions.md
  .kiro/steering/*.md, .cursor/rules/*.mdc|*.md, .github/instructions/*.instructions.md

Front matter (optional; Kiro's keys, with Cursor's and Copilot's mapped onto them):
  inclusion: always       in every request (the default)
  inclusion: fileMatch    with fileMatchPattern: "src/api/**/*.ts" (or a list): loaded the first time the
                          conversation reads or edits a matching file, or the user @-references one
  inclusion: manual       loaded when the user writes #name in a message
  inclusion: auto         with description: listed for the model, which loads it when relevant
Cursor rules: alwaysApply: true -> always, globs -> fileMatch, description only -> auto.
Copilot instructions: applyTo: "**" -> always, other applyTo -> fileMatch.
A body can include other workspace files with #[[file:relative/path]].
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_ALWAYS_CHARS = 24_000
MAX_DOC_CHARS = 20_000
MAX_FILE_REF_CHARS = 20_000
INCLUSIONS = ("always", "fileMatch", "manual", "auto")
ALWAYS_FILES = ("AGENTS.md", "CLAUDE.md", "CODEPILOT.md", ".cursorrules", ".windsurfrules",
                ".github/copilot-instructions.md")
FILE_REF = re.compile(r"#\[\[file:([^\]]+)\]\]")
MANUAL_REF = re.compile(r"(?<![\w#&/])#([A-Za-z][\w.-]*)")
NAME = re.compile(r"^[A-Za-z0-9][\w.-]{0,63}$")
TEMPLATE = """---
inclusion: {inclusion}{extra}
---

# {title}

Write standing instructions as short, specific statements, for example:

- Use pytest; put tests next to the code in tests/, named test_<module>.py.
- Never change public function signatures in api/ without updating docs/api.md.
"""


@dataclass
class Doc:
    name: str
    path: Path
    label: str  # how the user sees it: .codepilot/steering/x.md, ~/.codepilot/steering/x.md, CLAUDE.md
    scope: str  # workspace | global
    source: str  # codepilot | kiro | cursor | copilot | other
    inclusion: str
    body: str
    patterns: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def editable(self) -> bool:
        return self.source == "codepilot" or self.scope == "workspace"

    def info(self, root: Path | None) -> dict:
        rel = str(self.path.relative_to(root)) if root and self.scope == "workspace" else None
        return {"name": self.name, "label": self.label, "scope": self.scope, "source": self.source,
                "inclusion": self.inclusion, "patterns": self.patterns, "description": self.description,
                "editable": self.editable, "path": str(self.path), "rel": rel,
                "content": None if rel else self.path.read_text(errors="replace")[:MAX_DOC_CHARS]}


def front_matter(text: str) -> tuple[dict, str]:
    """A small YAML subset: `key: value`, `key: [a, b]`, and `key:` followed by `- item` lines."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict = {}
    key = None
    for line in m.group(1).splitlines():
        item = re.match(r"^\s*-\s+(.*)$", line)
        if item and key:
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(item.group(1).strip().strip("\"'"))
            continue
        k, sep, v = line.partition(":")
        if not sep or not k.strip() or k.startswith(" "):
            continue
        key, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[key] = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[key] = v.strip("\"'") if v else []
    return meta, m.group(2)


def _list(value) -> list[str]:
    if isinstance(value, list):
        return [v for v in value if v]
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


def parse(path: Path, label: str, scope: str, source: str) -> Doc | None:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    meta, body = front_matter(text)
    name = str(meta.get("name") or "") if source == "codepilot" else ""
    name = name or path.name.removesuffix(".instructions.md").removesuffix(".mdc").removesuffix(".md")
    description = str(meta.get("description") or "")[:300] if not isinstance(meta.get("description"), list) else ""
    if source == "cursor":
        globs = _list(meta.get("globs"))
        inclusion = "always" if str(meta.get("alwaysApply", "")).lower() == "true" else \
            "fileMatch" if globs else "auto" if description else "manual"
        patterns = globs
    elif source == "copilot":
        patterns = _list(meta.get("applyTo"))
        inclusion = "always" if any(p in ("**", "**/*", "*") for p in patterns) else \
            "fileMatch" if patterns else "manual"
    else:
        raw = str(meta.get("inclusion") or "always")
        inclusion = next((i for i in INCLUSIONS if i.lower() == raw.lower()), "always")
        patterns = _list(meta.get("fileMatchPattern"))
        if inclusion == "fileMatch" and not patterns:
            inclusion = "manual"
    return Doc(name=name, path=path, label=label, scope=scope, source=source, inclusion=inclusion,
               body=body.strip(), patterns=patterns if inclusion == "fileMatch" else [], description=description)


def discover(root: Path | None, home: Path, user_home: Path | None = None) -> list[Doc]:
    """Every steering doc for this workspace, global first. Same-named codepilot docs: the workspace wins."""
    user_home = user_home or Path.home()
    candidates: list[tuple[Path, str, str, str]] = []

    def add_dir(d: Path, label: str, scope: str, source: str, pattern: str = "*.md") -> None:
        if d.is_dir():
            candidates.extend((p, f"{label}/{p.name}", scope, source) for p in sorted(d.glob(pattern)) if p.is_file())

    candidates.append((home / "AGENTS.md", "~/.codepilot/AGENTS.md", "global", "other"))
    add_dir(home / "steering", "~/.codepilot/steering", "global", "codepilot")
    add_dir(user_home / ".kiro" / "steering", "~/.kiro/steering", "global", "kiro")
    if root is not None:
        candidates += [(root / f, f, "workspace", "other") for f in ALWAYS_FILES]
        add_dir(root / ".kiro" / "steering", ".kiro/steering", "workspace", "kiro")
        add_dir(root / ".cursor" / "rules", ".cursor/rules", "workspace", "cursor", "*.md*")
        add_dir(root / ".github" / "instructions", ".github/instructions", "workspace", "copilot", "*.instructions.md")
        add_dir(root / ".codepilot" / "steering", ".codepilot/steering", "workspace", "codepilot")
    docs: list[Doc] = []
    for path, label, scope, source in candidates:
        if not path.is_file():
            continue
        doc = parse(path, label, scope, source)
        if doc is None or not doc.body:
            continue
        if source == "codepilot":  # a workspace doc replaces the global one of the same name
            docs = [d for d in docs if not (d.source == "codepilot" and d.name == doc.name)]
        docs.append(doc)
    return docs


def fingerprint(root: Path | None, home: Path) -> str:
    """Changes when any steering doc is added, removed or edited, so new instructions apply on the next turn."""
    h = hashlib.sha1()
    for d in discover(root, home):
        try:
            st = d.path.stat()
        except OSError:
            continue
        h.update(f"{d.path}|{st.st_mtime_ns}|{st.st_size}\n".encode())
    return h.hexdigest()[:16]


def expand(body: str, root: Path | None) -> str:
    """Replace #[[file:path]] with that workspace file's content (never anything outside the workspace)."""
    def sub(m: re.Match) -> str:
        rel = m.group(1).strip()
        if root is None:
            return f"(file reference {rel}: no workspace open)"
        target = (root / rel).resolve()
        if target != root and root not in target.parents or not target.is_file():
            return f"(file reference {rel}: not found in the workspace)"
        text = target.read_text(errors="replace")
        if len(text) > MAX_FILE_REF_CHARS:
            text = text[:MAX_FILE_REF_CHARS] + "\n[... truncated ...]"
        return f"Contents of {rel}:\n```\n{text}\n```"
    return FILE_REF.sub(sub, body)


def render(doc: Doc, root: Path | None, why: str = "") -> str:
    body = expand(doc.body, root)
    if len(body) > MAX_DOC_CHARS:
        body = body[:MAX_DOC_CHARS] + "\n[... truncated ...]"
    return f'<steering name="{doc.name}" source="{doc.label}"{f" why={why!r}" if why else ""}>\n{body}\n</steering>'


def always_text(root: Path | None, home: Path) -> str:
    parts = [f"## {d.label}\n{expand(d.body, root)}" for d in discover(root, home) if d.inclusion == "always"]
    text = "\n\n".join(parts)
    if len(text) > MAX_ALWAYS_CHARS:
        text = text[:MAX_ALWAYS_CHARS] + "\n[... steering truncated; keep always-on docs short ...]"
    return text


def auto_listing(root: Path | None, home: Path) -> str:
    docs = [d for d in discover(root, home) if d.inclusion == "auto"]
    return "\n".join(f"- {d.name}: {d.description or '(no description)'}" for d in docs)


def glob_match(rel: str, pattern: str) -> bool:
    """Gitignore-style globs: ** spans folders, * stays within one, {a,b} alternatives. A pattern without a
    slash matches the file name anywhere (Cursor's "*.ts")."""
    pattern = pattern.strip()
    if pattern.startswith("./"):
        pattern = pattern[2:]
    if "/" not in pattern:
        rel = rel.rsplit("/", 1)[-1]
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif c == "*":
            out, i = out + "[^/]*", i + 1
        elif c == "?":
            out, i = out + "[^/]", i + 1
        elif c == "{":
            j = pattern.find("}", i)
            if j < 0:
                out, i = out + re.escape(c), i + 1
            else:
                out, i = out + "(?:" + "|".join(re.escape(x) for x in pattern[i + 1:j].split(",")) + ")", j + 1
        else:
            out, i = out + re.escape(c), i + 1
    return re.fullmatch(out, rel) is not None


def for_files(rels: list[str], root: Path | None, home: Path, already: set[str]) -> list[Doc]:
    """fileMatch docs that apply to any of these workspace paths and haven't been loaded yet."""
    found = []
    for d in discover(root, home):
        if d.inclusion == "fileMatch" and d.label not in already \
                and any(glob_match(r, p) for r in rels for p in d.patterns):
            found.append(d)
    return found


def requested(text: str, root: Path | None, home: Path) -> list[Doc]:
    """Docs the user named with #name in a message (any inclusion mode)."""
    names = set(MANUAL_REF.findall(text))
    if not names:
        return []
    return [d for d in discover(root, home) if d.name in names]


def find(name: str, root: Path | None, home: Path) -> Doc | None:
    return next((d for d in discover(root, home) if d.name == name), None)


def template(name: str, inclusion: str = "always", pattern: str = "") -> str:
    extra = f'\nfileMatchPattern: "{pattern}"' if inclusion == "fileMatch" else \
        "\ndescription: When to use this doc, in one line" if inclusion == "auto" else ""
    return TEMPLATE.format(inclusion=inclusion, extra=extra, title=name.replace("-", " ").replace("_", " ").title())


FOUNDATION_PROMPT = (
    "Create steering docs for this workspace, like Kiro's foundation files, so you and I follow the project's "
    "conventions in every future session. First investigate the repo (explore, read the README, build files, "
    "tests and a few representative modules). Then propose three files with propose_edit:\n"
    "- .codepilot/steering/product.md: what the product does, its users, key features and business rules.\n"
    "- .codepilot/steering/tech.md: languages, frameworks and key libraries, how to build, run, test and lint, "
    "and technical constraints.\n"
    "- .codepilot/steering/structure.md: the directory layout, where new code and tests go, naming, and "
    "architectural patterns to follow.\n"
    "Start each with front matter `---\\ninclusion: always\\n---`. Keep each under about 60 lines of concrete, "
    "verifiable statements taken from the code (no generic advice), and say where you weren't sure."
)
