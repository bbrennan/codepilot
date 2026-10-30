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
- [Steering](#steering)
- [Specs](#specs)
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
  runs tests, analyser checks or any command yourself. **Terminal** holds your shells (see
  [the terminal](#the-terminal)).
- **Title bar:** the open folder, file search (⌘P), the **Terminal** menu, and buttons to show or hide the
  sidebar, bottom panel and chat, and to switch theme.
- **Status bar:** provider and region, git branch, detected test command, GitHub login, how full the
  session's memory is, and tokens used.

All panes resize by dragging their edges. The layout (sizes, hidden panes, the open sidebar view and
bottom-panel tab) and the theme are remembered per browser.

## Start working on a folder

Either:
- click **Open folder…** (title bar or Explorer) and browse to the project, or
- just say it in chat: "Review ~/code/payments for bugs". codepilot asks before opening the folder.

A session is one conversation about one folder at a time. Make as many as you like (**+** in Sessions);
they run independently, so one can keep working while you look at another. Each session keeps its full
history, reopenable from the sidebar.

When a folder opens, codepilot reads:
- its steering: `.codepilot/steering/`, your global `~/.codepilot/steering/`, and other tools' files
  (`AGENTS.md`, `CLAUDE.md`, `.kiro/steering/`, `.cursor/rules/`, Copilot instructions). See
  [Steering](#steering)
- a map of its classes and functions, and its git status
- your notes for that folder (see [Memory](#memory))

## Files and folders

**Markdown files open as raw text**, like in VS Code, so you can read and **Edit** the source. Right-click
a file and choose **Open Preview**, or press **Preview** in its toolbar, to see it rendered like on GitHub:
headings, tables, task lists, links, images, highlighted code and **Mermaid diagrams** (**Source** goes back).
Links to other files in the repo open them (Markdown ones in preview), and `#section` links scroll within the document. While editing a Markdown file,
**Preview** shows your unsaved draft. **Drag files or folders from Finder/Explorer into the explorer** to add them to the workspace: onto a folder to put them in it, onto a file to put them beside it, onto empty space for the root. Nothing is replaced without asking, `.git` is off limits, and each file can be up to 100 MB. Image files open as images. Raw HTML in a document is cleaned before
display: scripts, event handlers, styles and forms are removed, so a document can't run code in codepilot.

You can manage files yourself, as in any IDE. Use the title-bar **File** menu, the **New File** and
**New Folder** buttons at the top of the Explorer, or right-click in the Explorer:

- **New File… / New Folder…** create the item in the selected folder (or next to the selected file).
  Right-click a folder to create inside it, or empty space to create at the top level. Type `/` in the
  name for subfolders, e.g. `utils/helpers.py`; missing folders are created. Existing files are never
  overwritten.
- **Edit:** the **Edit** button on an open file, or right-click → **Edit**, opens a plain-text editor. A
  new file opens in it straight away. **Save** (⌘S) writes the file; a ● on the tab means unsaved changes,
  and closing the tab asks first. **Done** returns to the highlighted view. If the file changed on disk
  since you opened it (you elsewhere, a tool, an applied proposal), Save asks before overwriting.
- **Rename…** (F2): a new name, or a workspace-relative path to move it. Open tabs follow the file.
- **Delete** (Delete or ⌘⌫): asks first, then moves the item to codepilot's trash
  (`~/.codepilot/trash`). **Undo** in the notification puts it back.

F2 and Delete work only while the Explorer has focus (you last clicked in it), so they never act from the
chat or editor. These are your own actions: they don't go through proposals or approvals, and they can't
reach outside the workspace folder.

**The Explorer and open files follow the disk.** Whatever changes the folder (the agent, a command in the
terminal, your other editor, git) shows up within about two seconds, and right after each agent step. An
open file reloads in place. If you have unsaved edits in it, they're kept and you're told it changed;
saving then asks before replacing the newer file. The ↻ button still forces a full reload.

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

**Commands:** type `/` for a menu of commands and skills. Commands act in the app straight away, with no
model call:

| Command | What it does |
|---|---|
| `/help` | List commands and skills |
| `/new` | New session on this folder |
| `/plan`, `/build`, `/debug`, `/review`, `/ask`, `/bughunt`, `/spec` (and custom modes) | Switch mode; text after it is sent, e.g. `/debug the total is wrong` |
| `/mode <mode>` | Switch mode by name |
| `/model auto` · `fast` · `main` · `hard` · `<name>` | Switch the model for this session, e.g. `/model opus` |
| `/spec <what to build>` | Start a spec from a description |
| `/init` | Draft steering docs (`product.md`, `tech.md`, `structure.md`) from the repo |
| `/compact [focus]` | Summarise the conversation to free context |
| `/retry` · `/undo` | Send your last message again · undo the last applied change |
| `/remember <fact>` | Add a line to this folder's notes |
| `/export` | Download the conversation as Markdown |
| `/terminal` · `/usage` · `/steering` | New terminal · context and tokens · steering docs |
| `/report` (or `/bug`) · `/restart` | Report a problem · restart the server |

Commands with no arguments run as soon as you pick them from the menu. A message that only starts with a
path (`/Users/me/app.py fails`) is sent as normal.

**Use a skill:** pick one from the same `/` menu, for example `/diagnose-bug the checkout total is wrong`.
See [skills-and-modes.md](skills-and-modes.md).

**Paste** with ⌘V, or with Ctrl+V on a Mac too, in the message box and every other text box (not the
terminal, where Ctrl+V belongs to the shell). For Ctrl+V the browser asks once to allow clipboard access;
if it was blocked, codepilot says how to allow it.

**Images:** paste a screenshot (⌘V, or Ctrl+V on a Mac too), drop image files on the message box, or click
the 🖼 button. Thumbnails appear above the box; ✕ removes one. Images are shrunk in the browser before
sending, and an image alone (no text) is fine. codepilot also attaches images you point at:
- an image link (`https://…/screen.png`);
- a local path, spaces and all: paste a macOS screenshot's path as it is
  (`~/Desktop/Screenshot 2026-10-25 at 3.14.15 PM.png`), quoted, or with `\ ` escapes;
- a workspace image, with or without `@` (`@"shots/login page.png"`, `docs/diagram.png`).

The assistant can also open images itself with `view_image`: one in the workspace (a screenshot a test
wrote, say), a URL, or a file elsewhere such as your Desktop, which asks you first. PNG, JPEG, GIF, WebP,
and HEIC on a Mac. Images too big to send (Retina screenshots often are) are shrunk automatically on a Mac;
elsewhere, paste them instead, since the browser shrinks what you paste. The model must support images
(Claude and GPT-4o-class models do; most small local models don't). To check that yours does, run
`uv run codepilot smoke --tier hard` (or `main`, `fast`).

**Earlier prompts:** press **↑** in the message box to bring back what you sent before, like a shell's
history: this session's prompts first, then ones from other sessions. **↓** goes forward, and past the
newest brings back what you were typing. In multi-line text, ↑ and ↓ move between lines first and recall
history only from the first or last line.

**Long pastes** (a trace, a log, a big JSON) are sent in full, but the chat shows only their first lines
with **Show all (N lines · size)** and **Copy**, so scrolling back through the conversation stays easy.

**While it works:** keep typing, and choose what your message does:

- **Queue** (Enter, or the **Queue** button): it waits, then runs as its own message once the current
  work finishes. Queue several and they run one after another.
- **Steer** (⌘Enter, Ctrl+Enter on Windows and Linux, or the **Steer** button): codepilot reads it at its
  next step, between tool calls, and carries on with it in mind ("use the v2 API instead", "keep it short").

A waiting message shows as *Steering* or *Queued*; **Run after instead** / **Steer now instead** switches
it, and **Edit** or **Remove** work until codepilot picks it up. **Stop** puts waiting messages back in
the box. A turn keeps running if you reload or close the page: open the session again and it picks up
where it is, with Stop, Steer and Queue working as before. If codepilot is waiting for you to approve a
command, writing a message instead declines the command, and your message goes to codepilot with that
decision.

**Edit or retry:** hover over one of your messages for ✎ **Edit** and ↻ **Retry**. Both rewind the
conversation to that message: everything after it is removed, then the (edited) message is sent again. A
message that was queued and read in the middle of a turn is part of that turn, so it has no Edit or Retry
of its own: edit the message that started the turn instead. Messages summarised by compaction can't be edited.
An error in the chat has a **Retry** button too.

**Undo a turn's file changes.** If changes were applied from that message onwards, Edit and Retry list them and
offer **Also undo these file changes** (ticked). Untick it to rewind the conversation only. To undo the changes but
keep the conversation, hover over the message and click ↶ **Undo file changes from here**; codepilot is told what
you undid with your next message. Either way, a change is undone only if its file still holds exactly what
codepilot wrote. One you've edited since is listed as "left as is", and so are older changes to that file. Only
changes codepilot applied are covered: what commands, the terminal or other editors changed isn't undone.

**Notifications:** if you switch to another tab or app, codepilot shows a desktop notification when it
finishes or needs your approval (your browser asks permission the first time).

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
| **Spec** | Bigger features and tricky bugs: requirements, design and tasks, each reviewed, then task by task ([specs.md](specs.md)) | Edit code before the task list is approved |
| **Review** | Reviewing changes or code against the intent and the repo's standards | Edit, unless asked |

You can switch mode mid-conversation, and you can add your own modes
([skills-and-modes.md](skills-and-modes.md#modes)).

## Changes: proposals, Apply, Undo

codepilot never writes to your files without you. Proposed changes collect in the **review bar** pinned
above the message box ("2 changes to review · +12 −3"), so they don't get lost as the chat scrolls. Each
one is also a single line in the chat; click it to see its diff.

- **Review** opens the **Review** tab: changed files on the left, the full diff on the right. Press
  <kbd>j</kbd>/<kbd>k</kbd> to move, <kbd>a</kbd> to apply and <kbd>r</kbd> to reject; after each decision
  it jumps to the next waiting change. To ask for something different, type it under the diff ("keep the
  old name as an alias"); that sends "About change #3 to …" to the chat.
- **Apply all** / **Reject all** in the bar decide everything at once.
- **It carries on by itself:** when you've decided every change it was waiting on and applied at least
  one, codepilot continues ("Continuing after your review"). It verifies what was applied, usually by
  running the relevant tests, and finishes the task. If you rejected everything, it waits for you.
- **Apply** writes it. codepilot then checks the file's syntax (and runs ruff on Python files, if
  installed) and tells the assistant what it found.
- **Reject** discards it. The assistant is told on your next message.
- **Undo** (on applied changes) restores the file exactly, as long as it hasn't changed since. To undo every
  change from one message onwards at once, use ↶ on that message (see [Talking to it](#talking-to-it)).

Changes only wait while they can still be applied. One that can't be applied any more stops waiting, and
the assistant is told:
- **outdated:** its file changed, for example you applied a newer version or edited the file yourself;
- **superseded:** the assistant proposed a new version of the same lines;
- **discarded:** you edited or retried an earlier message, so the turn that proposed it is gone.

After a restart, every change appears where it was proposed, with its current status. Only changes still
waiting show in the review bar.

**Verify before you apply.** Changes waiting for review aren't on disk, so a test run in the workspace would test
the old code. **Verify** in the review bar copies the workspace (instantly on APFS, as copy-on-write), applies the
waiting changes to the copy, and runs your test command and analysers there. The result shows under the changes:
- **✓ verified** · tests pass · ruff clean;
- **✗ 2 newly failing**, with **Details** (commands, exit codes, output) and **Ask codepilot to fix**;
- **✓ no new failures** when something also fails without the changes;
- **⚠ inconclusive** when tests fail both with and without the changes and the output doesn't show which failures
  are new.

Nothing is applied and your folder isn't touched. When the changes waiting for review change, the result is marked
"changed since" until you verify again. With **auto-run tests** ticked, codepilot verifies by itself when a turn ends
with changes waiting, and the assistant can verify its own changes with the `verify_changes` tool before handing
them to you. It is told the result. A virtualenv in the folder is copied too and pointed at the copy, so the tests
import the changed code. If that couldn't be done, the result says so instead of passing. Set `CODEPILOT_VERIFY=0`
to turn it off.

Prefer speed? `CODEPILOT_AUTO_APPLY=1` writes changes immediately; every one can still be undone.

codepilot **never commits, pushes or changes branches on its own**. Its git tool only reads. When you ask for a
commit, branch, merge or push, it runs the git command with `run_command`, so you approve each one. Before it does,
the turn context tells it whether the branch is behind its upstream, and whether a merge or rebase is half done with
conflicted files. Commands run without a terminal: an editor or password prompt fails at once instead of hanging.
The **Changes** view shows the working tree diff.

## Approvals: commands, tests, checks

| Action | Default |
|---|---|
| Reading files, searching, read-only git, traces | Runs freely |
| `run_tests` (the workspace's test command) | Asks. The "auto-run tests" box (or `CODEPILOT_AUTO_APPROVE_TESTS=1`) skips the prompt |
| `run_checks` (linters, type checkers, scanners) | Asks, with the same auto-run switch |
| `run_command` (any shell command) | Always asks, and shows the exact command |
| GitHub reads | Run freely |
| GitHub writes (comment, create, merge or close a PR, create an issue, re-run CI) | Always ask |
| Opening a different folder | Asks |

Approvals appear in the same **review bar** above the message box, with the exact command: **Run**
(or <kbd>⌘</kbd><kbd>⏎</kbd> from anywhere) or **Deny**. The chat keeps a one-line record ("Approved: …").
A pending approval is still there after a page reload.

**Always allow … in this session** (under the command) skips asking for commands that start the same way,
such as `pytest`, `npm test` or `make eval-bedrock`, until the session ends. It's never offered for commands
that chain or redirect (`;`, `&&`, `|`, `$( )`, `>`), and those always ask even when they start with an
allowed prefix. It's also never offered for `rm`, `sudo`, `git`, `curl` and similar. **Memory → Always allowed in this
session** lists the rules; remove any of them there.

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

The **Traces** view (the pulse icon) appears only when the open folder has trace or log files. It lists
JSON/JSONL trace and log files from folders named `traces/`, `logs/`, `eval_results/` or `results/` (add
more with `CODEPILOT_TRACE_DIRS`). Opening
one shows:

- record, span and error counts, total duration, and trace/session ids
- a **timeline** of spans, with failures in red (hover a bar for its attributes)
- the raw JSON as a collapsible tree

**Ask codepilot about this trace** starts an analysis: what happened, which step failed, and the code
responsible. This works with OpenTelemetry-style spans (AgentCore, Strands, LangGraph and others) and with
most structured JSON logs. With `CODEPILOT_LOG_GROUPS` set, it can also search CloudWatch Logs (read-only).

If your project has an end-to-end or eval command that writes results or traces, set `CODEPILOT_EVAL_CMD`.
It's pre-filled in **Output**, and the assistant can run it (with approval) to regenerate traces after a fix.

## GitHub

With `gh` logged in (status bar shows `github: <you>`), ask things like:
- "Summarise PR 42 and its review comments; which comments are still unaddressed?"
- "CI failed on my branch; read the failed job logs and fix the cause."
- "Find other repos in our org that call `get_price(`."
- "Draft a reply to the reviewer on PR 42" (posting it needs your approval).

## Memory

A session isn't a series of one-off prompts. It remembers in four layers:

1. **The conversation.** Every step includes the session's history: messages, tool calls and results. It's
   stored locally (`~/.codepilot/codepilot.db`) and survives restarts. Prompt caching keeps resending it
   cheap.
2. **Automatic context management.** Before **every** model call, including in the middle of a long task,
   codepilot estimates the request's size in tokens (calibrated from the provider's real counts) against the
   model's budget, which is its context window minus room for the reply:
   - **At 60%** (`CODEPILOT_PRUNE_AT`), bulky old tool outputs (file reads, test logs) outside the most recent
     context are replaced by one-line notes. The assistant can re-run a tool if it needs the output again.
   - **At 80%** (`CODEPILOT_COMPACT_AT`), earlier turns are rewritten into one structured summary (goal,
     decisions, work done, current state, next steps). Your latest turns stay word for word, and the plan,
     proposals, files touched, commands run, key identifiers, errors and the latest test results are carried
     over exactly. So are your own messages: your first message (the original task), your latest ten, and
     any that state a constraint ("never…", "don't…", "must…"), within about 1.5k tokens.
   - **If a provider still rejects a request as too long,** codepilot compacts harder and retries once.
   - **By hand:** type `/compact` (optionally with a focus, e.g. `/compact the API changes`) or click the
     context meter. **Memory → Continue in new session** starts a fresh session seeded with the summary.

   The status bar shows `context 42% · 78k/184k`. Hover for details; click to compact now.
3. **Recall.** Compaction never deletes anything: the original messages are archived in the database.
   When the assistant needs an exact detail the summary lacks (your exact words, a value, an error, a tool
   result), it searches them with the `recall` tool (BM25 keyword search, exact text back). With scope
   `workspace` it also searches earlier sessions on the same folder, e.g. "what did we decide about rounding
   last week?".
4. **Workspace notes.** One notes file per folder, which the assistant adds to (`remember`) and you can
   edit in the **Memory** view. Every future session on that folder reads it. Put conventions there, such
   as "tests need `make db-up` first".

Start a fresh session when you switch to an unrelated task. It's cheaper, and focus improves.

## Steering

Steering docs are standing instructions codepilot always follows: coding standards, how to build and test,
architecture, things it must never do. They're Markdown files in `.codepilot/steering/` (this workspace;
commit them) or `~/.codepilot/steering/` (all your workspaces), in Kiro's format.

- Open the **Steering** view (the compass in the activity bar) to see every doc and create new ones.
  **Generate foundation docs** has codepilot draft `product.md`, `tech.md` and `structure.md` from the repo.
- A doc can be **always** on (the default), apply **only to matching files** (`fileMatch`), load when you
  write **`#name`** in chat (`manual`), or load **when relevant** (`auto`).
- Edits apply from your next message. A **steering: name** chip in the chat shows when a doc loaded.

The full guide, with examples, is in [steering.md](steering.md).

## Specs

For bigger changes, open the **Specs** view (the list icon) → **New spec**, or switch to **Spec** mode and
describe what you want. codepilot writes **requirements** (EARS acceptance criteria), then a **design**,
then **tasks**, and you approve each in the **Spec** tab before the next. Then **Run** tasks one by one or
**Run all remaining**. **Check spec vs code** and **Verify with evals** keep the spec and the code in
step. Specs live in `.codepilot/specs/` in Kiro's format; Kiro and Spec Kit specs are listed too. Full
guide: [specs.md](specs.md).

## Web tools

Three built-in tools reach outside your machine. They're plain code in codepilot, not MCP servers, and
`CODEPILOT_WEB=0` turns them all off.

| Tool | What it does | Asks you? |
|---|---|---|
| `library_docs` | Current docs and code examples for a library or SDK, from [Context7](https://context7.com) (e.g. FastAPI, React, boto3, the Bedrock AgentCore SDK). Only the library name and question are sent | No |
| `web_fetch` | Reads a web page as text, or an image by URL | Yes, per site. "Always allow" covers that exact site for the session |
| `web_search` | Web results from Brave Search | No. Only offered when `BRAVE_API_KEY` is set (Brave's free tier: 2,000 queries a month) |

`web_fetch` never pre-approves any site, refuses redirects to a different site, and never fetches
cloud-metadata addresses. A fetched URL could carry data out, so read what you approve.
`CONTEXT7_API_KEY` (free from context7.com) raises Context7's rate limit.

## Model tiers and cost

Each provider has three tiers, **fast**, **main** and **hard**, plus **auto** (the default), which picks
one for each turn. The model dropdown in the chat header lists the tiers, then **only the models your
account can call** (found automatically by asking each one for a few tokens, and cached for 12 hours):
the newest of each family first, earlier versions under **Older versions**, and each version once even
when it's reachable several ways (Messages API, `us.` and `global.` profiles). Models that aren't enabled
are hidden; hover **Refresh model list** to see how many, and `codepilot models` lists them with the
reason. Pick a tier, or pin a specific model for the session.

**Each tier uses the newest model of its family on your account.** If `.env` says Sonnet 4.5 and Sonnet 4.6
is enabled, the main tier uses Sonnet 4.6 (hover the tier to see this). Set `CODEPILOT_LATEST_MODELS=0`
to use exactly the configured IDs. If a tier's family isn't enabled at all, it shows "(fallback)" and
uses the best enabled model of the next family. The `explore` sub-agent and memory summaries always use
**fast**.

**Auto** picks the model for each message by simple rules, and a chip in the chat shows its pick and why
("auto → claude-sonnet-5-5 · routine work"):

| Situation | Model |
|---|---|
| Routine work (most messages) | the newest **Sonnet** your account can use |
| Plan, Debug and Bug-hunt modes; big or structural changes (a long message, 3+ `@files`, "refactor", "architecture", "migrate"…); you write "think hard", "ultrathink" or "use opus"; the previous turn kept failing or ran out of steps | the newest **Opus** |
| A short question in Ask mode | the newest **Haiku** |

The model stays the same for the whole turn, which keeps prompt caching effective. If test or command runs
fail twice in one turn, Auto asks Opus once for a **second opinion** (shown as a card), and the next turn
starts on Opus. A specific tier or model you pick is used as-is. To compare Auto's cost and pass rate with a
fixed tier, run the benchmark with `--tier auto` ([benchmark.md](benchmark.md)).

Token use per model shows in **Memory → Token usage** and in the status bar. Costs are per token on your
provider's bill; prompt caching cuts the cost of the repeated context a lot. To compare models on your
kind of work, use the [benchmark](benchmark.md).

## The terminal

Real terminals, like VS Code's: your login shell with your usual prompt, PATH, aliases and credentials.
Interactive programs, colours, `git`, `vim`, `aws sso login` and so on all work. Open as many as you
like (up to 12 running at once).

- **Open one:** the **Terminal** menu in the title bar → **New Terminal** (in the session's folder),
  **New Terminal in Folder…** or **New Terminal in Home Folder**. Or click the **Terminal** tab in the
  bottom panel, or right-click a folder or file in the Explorer → **Open in Terminal**.
- **Switch:** the dropdown at the top of the Terminal panel (`1: zsh`, `2: dev server`, …), or pick one
  from the title-bar menu. The tab shows how many are open.
- **Toolbar:** **+** new terminal, ✎ rename (or double-click the dropdown), 🗑 kill, and a menu with
  everything else, including **Kill All Terminals**.
- **They keep running.** Terminals live in the codepilot server, not the page: reload the browser, switch
  panels or sessions, and each one is still there with its scrollback and state (a dev server keeps
  serving, `export`ed variables stay set). They end when you kill them, when the shell exits, or when
  codepilot stops.
- **Exiting:** `exit` closes the terminal. If the shell exits with an error code, the terminal stays open
  so you can read why; press any key to close it, or **Restart** for a new shell in the same folder.
- **Selection → chat:** select output (a stack trace, a failing test) and paste it into the chat as a code
  block.
- When you switch folders, existing terminals stay where they are; **+** opens one in the new folder.
- Shells run as you, so anything you type runs with your permissions. The assistant can't type into it;
  its commands go through `run_command` with your approval. Turn the terminal off with
  `CODEPILOT_TERMINAL=0` (see [security.md](security.md#the-terminal)).

## Terminal mode

Not the terminal panel: this runs the whole assistant in your terminal, without the browser.

```bash
uv run codepilot chat --repo ~/code/my-service [--tier hard]
```

The same agent in the terminal. Approvals are y/N prompts; use `/apply N` and `/reject N` for proposals,
and Ctrl-D to quit. `--session <id>` resumes a session.

## Help and problem reports

The **?** in the title bar has **Report a problem…**, **Documentation** and **Restart the server**.
A report can be downloaded as a file (full diagnostics, secrets removed) or opened as a pre-filled GitHub
issue (a short summary you review before submitting). Details: [troubleshooting](troubleshooting.md#getting-more-detail).

## Keyboard shortcuts

| Keys (⌘ = Ctrl on Linux) | Action |
|---|---|
| Ctrl+` | Toggle the terminal panel (the title-bar **Terminal** menu does everything without shortcuts) |
| ⌘P | Go to file |
| ⌘B | Toggle sidebar |
| ⌘J | Toggle bottom panel |
| ⌘L | Focus chat |
| ⌘C (file selected in Explorer) | Copy its path |
| F2 / Delete or ⌘⌫ (Explorer) | Rename / delete the selected file or folder |
| ⌘S | Save the file you're editing |
| ↑ / ↓ (message box) | Earlier / later prompts |
| Alt+W | Close editor tab |
| Enter / Shift+Enter | Send / new line |
| Enter / ⌘Enter (while it works) | Queue a message to run after / steer the running work |
| `@` / `/` / `#` | Reference a file / run a command or skill / attach a steering doc |
| Esc | Close popups |

## Tips for good results

- **Say what done looks like:** "fix it and make sure `pytest tests/billing` passes".
- **Give it evidence:** a stack trace, a failing test, a trace file, the exact input.
- **Use the right mode:** Plan before big changes; Debug for bugs; Review for reviews.
- **Reference files** with `@` instead of describing where things are.
- **Install the analysers** for your language. Real lint and type errors beat guesses.
- **Teach it once:** put conventions in a [steering doc](steering.md) (or ask codepilot to "add that to
  steering"); use "remember" for quick facts.
- **Read approvals,** especially `run_command`.
