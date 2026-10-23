# Using codepilot

- [The screen](#the-screen)
- [Start working on a folder](#start-working-on-a-folder)
- [Talking to it](#talking-to-it)
- [Modes](#modes)
- [Changes: proposals, Apply, Undo](#changes-proposals-apply-undo)
- [Approvals: commands, tests, checks](#approvals-commands-tests-checks)
- [Common workflows](#common-workflows)
- [Traces and logs](#traces-and-logs)
- [GitHub](#github)
- [Memory](#memory)
- [Model tiers and cost](#model-tiers-and-cost)
- [The terminal](#the-terminal)
- [Terminal mode](#terminal-mode)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Tips for good results](#tips-for-good-results)

## The screen

```
┌ title bar: folder · ⌘P search files · layout toggles ───────────────────────────────────────┐
│act│ sidebar          │ editor tabs (files, traces, diffs)            │ chat                  │
│bar│ Sessions         │                                               │ mode · tier           │
│   │ Explorer         │                                               │ transcript            │
│   │ Search           ├───────────────────────────────────────────────┤ plan checklist        │
│   │ Traces           │ bottom panel:                                 │ message box (@ and /) │
│   │ Changes · Memory │ Activity · Output (run) · Terminal            │                       │
└ status bar: provider · git branch · test command · GitHub user · context meter · tokens ────┘
```

- **Activity bar (far left):** switches the sidebar between Sessions, Explorer, Search, Traces, Changes and
  Memory. Click the active icon to collapse the sidebar.
- **Editor:** opens files (with syntax highlighting), trace timelines and diffs as tabs.
- **Chat (right):** the conversation, with every tool call shown as a card you can expand.
- **Bottom panel:** **Activity** lists every model call and tool call with timings and tokens. **Output**
  runs tests, analyser checks or any command yourself. **Terminal** is a real shell in the workspace.
- **Status bar:** provider and region, git branch, detected test command, GitHub login, how full the
  session's memory is, and tokens used.

All panes resize by dragging their edges; the layout and theme are remembered per browser.

## Start working on a folder

Either:
- click **Open folder…** (title bar or Explorer) and browse to the project, or
- just say it in chat: "Review ~/code/payments for bugs". codepilot asks before opening the folder.

A session is one conversation about one folder at a time. Make as many as you like (**+** in Sessions);
they run independently, so one can keep working while you look at another. Each session keeps its full
history, reopenable from the sidebar.

When a folder opens, codepilot reads:
- its instruction files, if any: `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.cursor/rules/`,
  `.kiro/steering/`, `.github/copilot-instructions.md`, plus your global `~/.codepilot/AGENTS.md` and
  `~/.kiro/steering/`
- a map of its classes and functions, and its git status
- your notes for that folder (see [Memory](#memory))

## Talking to it

Write as you would to a colleague. Be specific about the goal and what "done" looks like.

**Point at code:**
- Type `@` and pick a file from the autocomplete: `@src/billing/invoice.py`
- Reference lines: `@src/billing/invoice.py:40-80`
- Drag a file or folder from the Explorer into the message box.
- In an open file, click line numbers (shift-click for a range), then **Add lines**.
- Right-click any file for **Add to chat**, **Copy relative/absolute path** and **Copy @reference**.

Referenced files (or line ranges) are attached to your message automatically, so the assistant doesn't
have to go looking. Paths in its answers (`src/app.py:42`) are links that open the file at that line.

**Use a skill:** type `/` to pick one, for example `/diagnose-bug the checkout total is wrong`. See
[skills-and-modes.md](skills-and-modes.md).

**Stop:** the stop button halts a running turn at the next safe point.

## Modes

Pick a mode in the chat header. Each is a focused agent with its own instructions, tools and skills.

| Mode | Use it for | What it won't do |
|---|---|---|
| **Ask** | Questions, explanations, "how does X work?" | Run anything or propose edits |
| **Plan** | Larger changes: investigate, then agree a plan | Edit or run commands |
| **Build** (default) | Implementing changes end to end, verified by tests and checks | |
| **Debug** | A specific bug: reproduce, find the root cause, fix, add a regression test | |
| **Bug-hunt** | Searching for real bugs, each confirmed with evidence | Edit (switch to Debug to fix) |
| **Review** | Reviewing changes or code against the intent and the repo's standards | Edit, unless asked |

You can switch mode mid-conversation, and you can add your own modes
([skills-and-modes.md](skills-and-modes.md#modes)).

## Changes: proposals, Apply, Undo

codepilot never writes to your files without you. A change arrives as a **diff card** (in chat, in an editor
tab, and in the **Changes** view):

- **Apply** writes it. codepilot then checks the file's syntax (and runs ruff on Python files, if
  installed) and tells the assistant what it found.
- **Reject** discards it. The assistant is told on your next message.
- **Undo** (on applied changes) restores the file exactly, as long as it hasn't changed since.

Prefer speed? `CODEPILOT_AUTO_APPLY=1` writes changes immediately; every one can still be undone.

codepilot **never commits, pushes or changes branches**. Use git yourself; the **Changes** view shows the
working tree diff.

## Approvals: commands, tests, checks

| Action | Default |
|---|---|
| Reading files, searching, read-only git, traces | Runs freely |
| `run_tests` (the workspace's test command) | Asks. The "auto-run tests" box (or `CODEPILOT_AUTO_APPROVE_TESTS=1`) skips the prompt |
| `run_checks` (linters, type checkers, scanners) | Asks, with the same auto-run switch |
| `run_command` (any shell command) | Always asks, and shows the exact command |
| GitHub reads | Run freely |
| GitHub writes (comment, create PR or issue, re-run CI) | Always ask |
| Opening a different folder | Asks |

Commands run on your machine, in the workspace folder, as you. Read them before approving. The assistant
also has a scratch folder (`~/.codepilot/scratch/<session>/`) for throwaway reproduction scripts, so it can
prove a bug without touching your code.

## Common workflows

**Review my changes.** "Review my uncommitted changes" or "review this branch against main". Use **Review**
mode for a pure review.

**Fix a failing test.** In **Debug** mode: "tests/test_cart.py::test_totals fails, fix it." It runs the
test (approve it), reads the code, reproduces the failure, proposes a fix plus a regression test, and
re-runs after you apply.

**Investigate a bug report.** Paste the report or the stack trace into **Debug** mode. It builds a
reproduction first (a test or scratch script), then fixes the root cause.

**Find bugs proactively.** **Bug-hunt** mode: "hunt for bugs in src/payments". It runs the analysers, explores
risky areas in parallel, and reports only bugs it could demonstrate.

**Build a feature.** Start in **Plan**: "add CSV export to the reports page". Agree the plan, switch to
**Build**, and it implements step by step with tests.

**Understand a codebase.** **Ask** mode: "map this codebase: entry points, main components, data flow".

**Security pass.** `/security-review src/api`.

## Traces and logs

The **Traces** view lists JSON/JSONL trace and log files from folders named `traces/`, `logs/`,
`eval_results/` or `results/` in the workspace (add more with `CODEPILOT_TRACE_DIRS`). Opening one shows:

- record, span and error counts, total duration, and trace/session ids
- a **timeline** of spans, with failures in red (hover a bar for its attributes)
- the raw JSON as a collapsible tree

**Ask codepilot about this trace** starts an analysis: what happened, which step failed, and the code
responsible. This works with OpenTelemetry-style spans (AgentCore, Strands, LangGraph and others) and with
most structured JSON logs. With `CODEPILOT_LOG_GROUPS` set, it can also search CloudWatch Logs (read-only).

If your project produces traces with a command (an eval or mock-journey run), set `CODEPILOT_EVAL_CMD`.
It's pre-filled in **Output**, and the assistant can run it (with approval) to regenerate traces after a fix.

## GitHub

With `gh` logged in (status bar shows `github: <you>`), ask things like:
- "Summarise PR 42 and its review comments; which comments are still unaddressed?"
- "CI failed on my branch; read the failed job logs and fix the cause."
- "Find other repos in our org that call `get_price(`."
- "Draft a reply to the reviewer on PR 42" (posting it needs your approval).

## Memory

A session isn't a series of one-off prompts. It remembers in three layers:

1. **The conversation.** Every turn includes the session's history: messages, tool calls and results. It's
   stored locally (`~/.codepilot/codepilot.db`) and survives restarts. Prompt caching keeps resending it
   cheap.
2. **The rolling summary.** When the conversation passes `CODEPILOT_CONTEXT_CHARS`, older turns are
   summarised by the fast model and the latest turns are kept word for word. The status bar's
   **context %** shows how close you are.
3. **Workspace notes.** One notes file per folder, which the assistant adds to (`remember`) and you can
   edit in the **Memory** view. Every future session on that folder reads it. Put conventions there, such
   as "tests need `make db-up` first".

Start a fresh session when you switch to an unrelated task. It's cheaper, and focus improves.

## Model tiers and cost

Each provider has three tiers: **fast**, **main** (default) and **hard**. Pick one per session in the chat
header. The `explore` sub-agent and memory summaries always use **fast**. Rough guide: **main** for nearly
everything, **hard** for gnarly bugs and big designs, **fast** for quick questions.

Token use per model shows in **Memory → Token usage** and in the status bar. Costs are per token on your
provider's bill; prompt caching cuts the cost of the repeated context a lot. To compare models on your
kind of work, use the [benchmark](benchmark.md).

## The terminal

**Terminal** in the bottom panel (or **Ctrl+`**) opens your login shell in the session's folder, with your
usual prompt, PATH, aliases and credentials. It's a full terminal: interactive programs, colours,
`git`, `vim`, `aws sso login` and so on.

- **Selection → chat:** select output (a stack trace, a failing test) and paste it into the chat as a code
  block.
- **New terminal:** closes the shell and starts a fresh one in the current workspace. When you switch
  folders, the existing shell stays where it was until you click this.
- The shell runs as you, so anything you type runs with your permissions. The assistant can't type into it;
  its commands go through `run_command` with your approval. Turn the terminal off with
  `CODEPILOT_TERMINAL=0` (see [security.md](security.md#the-terminal)).

## Terminal mode

Not the terminal panel: this runs the whole assistant in your terminal, without the browser.

```bash
uv run codepilot chat --repo ~/code/my-service [--tier hard]
```

The same agent in the terminal. Approvals are y/N prompts; use `/apply N` and `/reject N` for proposals,
and Ctrl-D to quit. `--session <id>` resumes a session.

## Keyboard shortcuts

| Keys (⌘ = Ctrl on Linux) | Action |
|---|---|
| Ctrl+` | Toggle the terminal |
| ⌘P | Go to file |
| ⌘B | Toggle sidebar |
| ⌘J | Toggle bottom panel |
| ⌘L | Focus chat |
| ⌘C (file selected in Explorer) | Copy its path |
| Alt+W | Close editor tab |
| Enter / Shift+Enter | Send / new line |
| `@` / `/` | Reference a file / use a skill |
| Esc | Close popups |

## Tips for good results

- **Say what done looks like:** "fix it and make sure `pytest tests/billing` passes".
- **Give it evidence:** a stack trace, a failing test, a trace file, the exact input.
- **Use the right mode:** Plan before big changes; Debug for bugs; Review for reviews.
- **Reference files** with `@` instead of describing where things are.
- **Install the analysers** for your language. Real lint and type errors beat guesses.
- **Teach it once:** put repo conventions in `AGENTS.md`, or ask it to "remember" them.
- **Read approvals,** especially `run_command`.
