# Steering

Steering docs are standing instructions codepilot follows in every conversation: your coding standards,
how the project is built and tested, its architecture, and things it must never do. Write them once instead
of repeating them in chat.

They use **Kiro's format**, so a steering folder works in both tools. codepilot also reads the instruction
files Claude Code, Cursor, GitHub Copilot and others use, with each tool's own rules for when they apply.

- [Where steering docs live](#where-steering-docs-live)
- [When a doc applies: inclusion modes](#when-a-doc-applies-inclusion-modes)
- [Writing good steering](#writing-good-steering)
- [The Steering view](#the-steering-view)
- [Other tools' files](#other-tools-files)
- [How it works](#how-it-works)

## Where steering docs live

| Folder | Applies to |
|---|---|
| `<workspace>/.codepilot/steering/*.md` | That workspace. Commit it so your team shares it |
| `~/.codepilot/steering/*.md` | Every workspace on your machine (your personal rules) |

A workspace doc overrides a global one with the same file name. For example, a repo's `testing.md`
replaces your personal `testing.md`.

## When a doc applies: inclusion modes

Set the mode in front matter at the top of the file. Without front matter, a doc is always on.

```markdown
---
inclusion: fileMatch
fileMatchPattern: "api/**/*.py"
---

# API conventions

- Every endpoint validates input with the schemas in api/schemas.py.
- Return errors as {"error": {"code", "message"}}; never raise bare exceptions to the client.
```

| `inclusion` | When codepilot uses it | Good for |
|---|---|---|
| `always` (default) | Every request | Coding standards, the stack, the project's layout, hard rules |
| `fileMatch` | The first time a conversation reads or edits a file matching `fileMatchPattern`, or you `@`-reference one | Rules for one area: API handlers, React components, migrations, tests |
| `manual` | When you write `#name` in a message (type `#` to pick one) | Checklists and playbooks: `#release`, `#incident`, `#security-review` |
| `auto` | Its `description` is listed for the model, which loads it when the task matches | Longer guides you don't want in every request |

**Patterns** (`fileMatchPattern`, one string or a list):
- `**` spans folders and `*` stays within one, so `src/**/*.ts` matches any `.ts` file under `src/`.
- `{a,b}` gives alternatives: `**/*.{ts,tsx}`.
- A pattern without `/` matches the file name anywhere: `*.sql`, `Dockerfile`.

**`auto` docs** need a `description` saying when to use them:

```markdown
---
inclusion: auto
description: Performance work, profiling, slow queries, caching
---
```

**Including other files:** `#[[file:docs/api-spec.yaml]]` in a doc inserts that workspace file's content,
so a steering doc can point at the real OpenAPI spec or schema instead of copying it. Only files inside the
workspace can be included.

## Writing good steering

- **Be specific and checkable.** "Use pytest fixtures from `tests/conftest.py`; no `unittest.TestCase`"
  beats "write good tests".
- **Say why for anything surprising.** "Don't use `datetime.now()`: all times are UTC via `clock.now()` so
  tests can freeze time."
- **Keep always-on docs short.** They're sent with every request; together, aim for a page or two.
  Move area-specific rules to `fileMatch` docs and long guides to `auto` or `manual` ones.
- **Write down only what the code doesn't say.** In the Steering view, **Draft conventions** (or `/init`) has
  codepilot study the repo and propose one short `conventions.md`, as a reviewable diff: non-standard build or test
  steps, forbidden patterns, constraints and gotchas, one line each, naming the file or command that shows it. It
  leaves out overviews of the product, stack and layout, and proposes nothing if it finds nothing non-obvious. If
  `conventions.md` exists, it proposes additions.
- **Why not overviews?** An ETH Zurich study of AGENTS.md-style context files (ICLR 2026) found they generally didn't
  improve task success and added over 20% to inference cost; overviews in particular didn't help, while
  non-standard practices were worth writing down. The study used only Python benchmarks, so treat it as
  suggestive. Either way, an always-on doc is paid for on every message.
- **Kiro foundation docs, on request:** **Draft Kiro foundation docs** (the Steering view's **+** menu) or
  `/init foundation` proposes `product.md`, `tech.md` and `structure.md`, the same three files Kiro generates.
- **Keep them current.** When codepilot learns a convention, ask it to "add that to steering". It proposes
  the edit like any other change.

## The Steering view

Click the compass in the activity bar. It shows:

- every doc, grouped: **This workspace**, **All workspaces**, **From other tools**;
- each doc's mode as a badge (`always`, its file pattern, `#name`, `auto`);
- **New steering doc**, which asks where it goes and what mode, creates it from a template and opens it in
  the editor;
- **Draft conventions** (see above), and how many tokens always-on docs add to each message, in total and per doc
  (`≈340 tok`). It's an estimate, from the same characters-per-token ratio as the context meter. Only always-on
  docs have a number, because the others aren't sent every time.

Click a doc to open it. Workspace and global docs are editable (**Edit**, then **Save** or ⌘S); other
tools' files open read-only. Changes apply from your next message, not just in new sessions.

In chat:
- type `#` to attach a steering doc to a message;
- a **steering: name** chip shows whenever docs load, including "for agent/core.py" when a `fileMatch`
  doc kicked in.

## Other tools' files

codepilot also reads these, so a repo set up for another assistant behaves the same here:

| File | Treated as |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, `CODEPILOT.md`, `.cursorrules`, `.windsurfrules`, `.github/copilot-instructions.md` | always on |
| `.kiro/steering/*.md`, `~/.kiro/steering/*.md` | Kiro front matter, exactly as above |
| `.cursor/rules/*.mdc` | `alwaysApply: true` → always; `globs` → fileMatch; only a `description` → auto; otherwise manual |
| `.github/instructions/*.instructions.md` | `applyTo: "**"` → always; other `applyTo` globs → fileMatch |
| `~/.codepilot/AGENTS.md` | always on, every workspace |

## How it works

- **Always-on docs** go in the system prompt, after the instructions codepilot itself sets.
- **Changes take effect on your next message:** codepilot notices any steering file being added, edited or
  removed, and rebuilds the system prompt then.
- **`fileMatch` docs** are added to the result of the `read_file` or `propose_edit` call that touched a
  matching file, or to your message when you `@`-reference one. Each loads once per session; after a
  context compaction they load again when they next apply.
- **`#name` docs** are attached to the message where you name them.
- **`auto` docs** are listed by name and description, and the model loads them with `load_skill`.
- **Limits:** always-on steering is capped at about 24k characters in total (it says when it truncates),
  and each other doc at 20k.
