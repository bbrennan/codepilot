# Skills and modes

Two ways to shape how codepilot works, both plain Markdown files:

- **Skills** are reusable workflows ("how we debug", "how to review"). They load only when needed.
- **Modes** are focused agents (Ask, Plan, Build, Debug, Bug-hunt, Review, and your own). Each combines
  instructions, tool restrictions, preloaded skills and an optional model tier.

## Skills

codepilot uses the open **Agent Skills** format: a folder containing `SKILL.md`. It's the same format
Claude Code, Kiro and the [skills.sh](https://www.skills.sh/) directory use.

```markdown
---
name: release-notes
description: Draft release notes from merged PRs since the last tag. Use when asked for release notes or a changelog.
---
# Release notes
1. Find the last tag: `git describe --tags --abbrev=0`.
2. List merged PRs since then with the github tool: `pr list --state merged --search "merged:>DATE"`.
...
```

- Only the `name` and `description` are always in context. The model calls `load_skill` to read the body
  when a task matches, so having many skills costs little.
- Add `disable-model-invocation: true` to make a skill **user-only**. It's hidden from the model and runs
  only when you type `/name`.
- Type `/` in chat to list skills; `/name extra words` runs one with your extra instructions.

### Built-in skills

| Skill | Purpose |
|---|---|
| `diagnose-bug` | A feedback loop first (failing test or repro script), then ranked hypotheses, root-cause fix, regression test and verification |
| `tdd` | Red, green, refactor, one small vertical slice at a time |
| `code-review` | Two axes: correctness against intent, and design against the repo's standards |
| `plan-feature` | Clarifying questions, then an approach and a verifiable step-by-step plan |
| `refactor-safely` | Characterization tests first, then small behaviour-preserving steps |
| `security-review` | Trust boundaries, injection, auth, secrets, and LLM-agent risks |
| `write-tests` | Tests that follow the repo's existing conventions |
| `resolve-merge-conflicts` | Merge both sides' intent, then verify |
| `agent-trace-triage` | Find the failing step in an agent run from its traces, then the code responsible |
| `/grill` (user-only) | Interviews you to stress-test a design |
| `/handoff` (user-only) | A summary so a fresh session can continue where this one stopped |

Their workflows are adapted from popular open skills on [skills.sh](https://www.skills.sh/), notably
[mattpocock/skills](https://github.com/mattpocock/skills) (MIT) and obra/superpowers, rewritten for
codepilot's tools.

### Where skills are loaded from

Later entries win when names clash:

1. codepilot's built-in skills (`codepilot/skills_bundled/`)
2. `~/.codepilot/skills/`, `~/.agents/skills/` and `~/.kiro/skills/`
3. folders in `CODEPILOT_SKILL_DIRS` (e.g. `~/.claude/skills` to reuse Claude Code skills)
4. the workspace's `.agents/skills/`, `.claude/skills/` and `.codepilot/skills/`

### Installing community skills

The [skills CLI](https://github.com/vercel-labs/skills) installs a repo's skills into the folder of the
agent you name with `-a`. Target one that codepilot reads:

```bash
npx skills add owner/repo -a claude-code      # this project: ./.claude/skills (codepilot reads it)
```

For skills meant for every project, copy the skill folders into `~/.codepilot/skills/`, or point codepilot
at an existing folder, for example `CODEPILOT_SKILL_DIRS=~/.claude/skills`. You can also just copy any
`<name>/SKILL.md` folder into `<workspace>/.agents/skills/` or `.codepilot/skills/`.

**Vet third-party skills before installing them.** A skill is a set of
instructions the model will follow inside your codebase. Skills written for Claude Code may mention tools
codepilot doesn't have (slash commands, subagents); they usually still work, but read them first.

### Project instruction files

Not skills, but related: codepilot follows the instruction files other assistants use, so a repo set up for
them behaves the same here. These are `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.cursor/rules/*.mdc`,
`.windsurfrules`, `.github/copilot-instructions.md`, `.kiro/steering/*.md` (Kiro's `inclusion: manual` and
`fileMatch` files are skipped) and `CODEPILOT.md`. They're always in context, plus your global
`~/.codepilot/AGENTS.md` and `~/.kiro/steering/*.md`.

<a id="modes"></a>
## Modes

A mode is the same agent loop with different settings. The built-ins:

| Mode | Instructions | Blocked tools | Preloaded skill |
|---|---|---|---|
| `ask` | Answer and explain; read-only | `propose_edit`, `write_scratch`, `run_command`, `run_tests`, `run_checks` | |
| `plan` | Investigate, produce an agreed plan | `propose_edit`, `write_scratch`, `run_command` | `plan-feature` |
| `build` (default) | Implement end to end, verify with tests and checks | | |
| `debug` | Follow `diagnose-bug` strictly | | `diagnose-bug` |
| `bughunt` | Prioritise risky code, explore in parallel, confirm each bug, report | `propose_edit` | |
| `review` | Review against intent and standards; verify findings | `propose_edit` | `code-review` |

### Custom modes

Create `~/.codepilot/modes/<name>.md` (all projects) or `<workspace>/.codepilot/modes/<name>.md` (one
project):

```markdown
---
name: perf
label: Perf
description: Find and fix performance problems, with measurements
tier: hard                        # optional: fast | main | hard
blocked: run_command              # optional: comma-separated tool names to disable
skills: diagnose-bug              # optional: comma-separated skills to preload
---
PERF MODE: measure before changing anything. Establish a baseline benchmark, profile to find the hot path,
change one thing at a time, and report before/after numbers.
```

It appears in the mode picker right away; reopen the session to refresh the list. Tool names you can
block: `open_workspace`, `list_files`, `read_file`, `search_code`, `git`, `explore`, `run_tests`,
`run_checks`, `run_command`, `list_traces`, `trace_outline`, `search_traces`, `read_trace`, `write_scratch`,
`propose_edit`, `update_plan`, `load_skill`, `recall`, `remember`, `github`, `cloudwatch_logs`.

### How modes reach the model

The session's system prompt stays fixed. When you switch modes, the new mode's instructions (and
preloaded skills) are sent once, with your next message. Blocked tools stay visible to the model but
return a "disabled in this mode" result. Keeping the system prompt fixed keeps prompt caching effective,
and on the newest Claude models it keeps earlier reasoning valid.
