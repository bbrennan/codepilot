# Architecture

codepilot is a small Python app: a model-agnostic agent loop, a set of sandboxed tools, a local web server
with a streaming API, and a single-page IDE front end with no build step.

```
browser (static/index.html, app.js, app.css)
   │  fetch + NDJSON streaming; WebSocket for the terminal; localhost only
   ▼
server.py (Starlette)  ──► agent.py ──► provider: bedrock.py | anthropic_api.py | openai_api.py | ollama.py
   │                          │
   │                          ├─► tools.py ──► files, search (rg), git, tests/commands, traces.py, checks.py,
   │                          │                github.py (gh), scratch, proposals
   │                          ├─► modes.py, skills.py, prompts.py, repomap.py, mentions.py
   ▼                          ▼
store.py (SQLite in ~/.codepilot): sessions, messages, proposals, usage, notes
```

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | Reads `.env` and the environment into a frozen `Config` |
| `agent.py` | The loop: model → tool calls → results → model, with approvals, Stop, the `explore` sub-agent, memory compaction, and the frozen system prompt plus per-turn context |
| `bedrock.py` | Converse streaming, tool use, prompt-cache points, error explanations, TLS |
| `anthropic_api.py` | Anthropic Messages API via the official SDK; adaptive thinking, block binding, fallbacks, caching |
| `openai_api.py` | Chat Completions with function tools via the official SDK; any compatible endpoint |
| `ollama.py` | Local models via Ollama's chat API |
| `tools.py` | Tool definitions, schemas, approval rules, execution and argument coercion |
| `traces.py` | Format-agnostic span extraction from JSON/JSONL traces |
| `checks.py` | Detects and runs linters, type checkers and security scanners; post-apply quick check |
| `github.py` | `gh` command classification (read/write/refused) and execution |
| `gitcmd.py` | What the read-only git tool may run (e.g. `git branch` lists, but never deletes or creates) |
| `gitstate.py` | The git state in each turn context: upstream, ahead/behind, merge or rebase in progress, conflicts |
| `procenv.py` | How commands run: non-interactive (no editor, prompt, pager or stdin), killed as a process group on timeout |
| `modes.py` | Built-in and custom modes |
| `skills.py` | SKILL.md discovery and slash commands |
| `specs.py` | Specs (Kiro format): phases, approvals, task parsing |
| `spec_profiles.py` | How much review a spec gets (full or quick): what may be written and approved when, and the instructions |
| `spec_reminder.py` | The task reminder during long implementation turns |
| `router.py` | Auto model routing: the per-turn rules, and failed-run detection for the second opinion |
| `steering.py` | Steering docs (Kiro format, plus Cursor, Copilot and other instruction files): discovery, inclusion modes, glob matching, `#[[file:]]` references |
| `repomap.py` | Symbol map of the workspace (Python via `ast`, others via regex) |
| `mentions.py` | `@file` references and fuzzy file search |
| `prompts.py` | System prompt text and assembly |
| `context.py` | Context-window management: token estimates, tool-output pruning, summaries, overflow recovery |
| `store.py` | SQLite persistence with additive migrations |
| `verification.py` | Verification receipts: clone the workspace, re-point copied virtualenvs, apply pending changes, run tests and analysers, and name what newly fails |
| `approval_policy.py` | Which tool calls need a human right now: destructive commands, and sessions that read external content. Advisors feed one `advise` call, so a new check is added, not branched in |
| `deps_guard.py` | Package guard: what a command or manifest edit would install, and what PyPI, npm and crates.io say about it |
| `shellparse.py` | Reads a command line as the shell would: which programs it runs, through chains and wrappers like `sudo` |
| `pricing.py` | Tokens to dollars, shared by the app and the benchmark. A model with no price is unpriced, never $0 |
| `spend.py` | What this has cost, per session, per turn and today, and the optional daily cap |
| `plans.py` | The plan checklist's lifecycle: new, update, complete, clear and restore, the same live and on reload |
| `checkpoints.py` | Turn checkpoints: the changes applied from a message onwards, and undoing them together (guarded like Undo) |
| `server.py` | HTTP API, NDJSON streaming, localhost and CSRF guards, static files, terminal endpoints. Blocking filesystem and git work runs in worker threads so it can't stall streams or terminals |
| `terminal.py` | Server-side terminals: PTY shells with scrollback that outlive the page, bridged to xterm.js over WebSockets |
| `service.py` | `codepilot start/stop/status/logs` (background server) and the macOS launcher (`codepilot app`) |
| `bench.py` | Benchmark runner, grading, reports, comparison, task validation |
| `cli.py` | `serve`, `doctor`, `chat`, `bench` |

## One turn, step by step

1. `POST /api/sessions/{id}/chat` → `Agent.chat()`.
2. Before every model call (step 4 onwards), `context.py` checks the request's estimated size and prunes old
   tool outputs or summarises earlier turns if needed; a 'too long' error triggers one compact-and-retry.
3. The user message is stored, with attachments (`@file` contents, an invoked `/skill`) and a
   `<turn_context>` block (current mode, git state, proposal outcomes) appended.
4. `_loop()` sends the **frozen session system prompt**, the tool specs and the live messages to the
   provider, streaming text to the browser.
5. For each tool call: blocked by mode → error result; needs approval → the turn pauses
   (`approval_needed`) until `POST /approve` resumes it; otherwise the tool runs. Results go back as one
   user message.
6. The loop repeats until the model stops calling tools, the step limit is reached, or the user presses Stop.

Every function in the loop is a generator of **events** (`text`, `thinking`, `tool_call`, `tool_result`,
`proposal`, `approval_needed`, `plan`, `sub_tool`, `workspace`, `usage`, `context`, `notice`, `error`,
`done`, ...). The server streams them as NDJSON; the terminal chat and the benchmark consume the same
stream.

## Messages and providers

Messages are stored in the **Bedrock Converse** shape (`text`, `toolUse`, `toolResult`,
`reasoningContent`). Each provider converts to and from its own wire format, so the agent and storage are
provider-agnostic. Thinking blocks keep their signatures so they can be replayed unchanged.

**Why the system prompt is frozen:** the newest Claude models bind each reasoning block to the exact
conversation prefix that produced it (system prompt, tools, earlier messages), and prompt caching also
needs a stable prefix. So the system prompt is computed once per session and reused. Things that change
(mode, git status, proposal outcomes) go into the user message instead. At the rare boundaries that must
change the prefix (memory compaction, switching workspace), stored reasoning blocks are removed once. The
Anthropic provider also sends `prefix_mismatch_behavior: "drop_block"` so a mismatch degrades instead of
failing.

## Extending

- **A tool:** write `fn(ctx, **args) -> str` in `tools.py` (raise `ToolError` for model-visible errors),
  register a `Tool(...)` in `build_tools()` with a JSON schema, and set `needs_approval`, `read_only` and
  `needs_workspace` appropriately. Add a test.
- **A provider:** a class with `stream(model, system, messages, tools, max_tokens)` (yielding events and a
  final `{"type": "message", ...}`), `complete()` and `list_models()`. Then register it in
  `agent.make_llm()` and `config.PROVIDERS`.
- **A mode or skill:** Markdown files; see [skills-and-modes.md](skills-and-modes.md).
- **A benchmark task:** see [benchmark.md](benchmark.md#adding-a-task).

## Front end

`static/index.html` is the layout. `app.css` holds the theme tokens, with dark and light variants.
`app.js` is plain DOM with no framework or build step. A feature with its own UI gets its own classic script
(`checkpoints.js`, `verify.js`, `plan.js`, `policy.js`, `deps.js`, `cost.js`), loaded after `app.js` and using its helpers, so `app.js` only wires it in. It vendors highlight.js (BSD-3) for highlighting and
xterm.js (MIT) for the terminal; see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
