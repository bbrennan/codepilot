# Benchmark

`codepilot bench` measures how well codepilot fixes real bugs, so you can compare models, modes and prompt
changes with numbers instead of impressions.

Each task is a small project with a planted bug (or a small feature request) and **hidden tests** the agent
never sees. codepilot gets the task's prompt, works headless, and the hidden tests decide pass or fail.

## Quick start

```bash
make bench-validate                 # sanity-check the tasks (no model calls)
uv run codepilot bench list         # the tasks
uv run codepilot bench run          # all tasks on the configured provider, main tier
```

Each task typically takes somewhere around 5 to 20 model calls, so a full run is a meaningful but modest
spend. This is an estimate, not a measurement: check the token totals in your first report, and add
`--prices` for a cost figure. Try one task first:

```bash
uv run codepilot bench run --tasks pagination-off-by-one
```

Results go to `bench/results/<timestamp>[-label]/`:
- `report.md`: pass rate, per-category and per-task table, tokens, time, and failure details
- `results.json`: everything, machine-readable (for `compare`)
- `transcripts/<task>.jsonl` and `<task>.diff`: what the agent did and what it changed

## Comparing

```bash
uv run codepilot bench run --tier main --label sonnet
uv run codepilot bench run --tier hard --label opus
uv run codepilot bench run --tier auto --label auto   # does Auto keep the pass rate at lower cost?
uv run codepilot bench compare bench/results/*-sonnet/results.json bench/results/*-opus/results.json
```

Useful comparisons:
- **Models:** `--tier auto|fast|main|hard`, or change the provider and model IDs in `.env` between runs.
  Reports list the tokens each model used, and with `--prices` cost is computed per model, so Auto runs
  (several models) and the explore sub-agent (the fast model) are priced correctly.
- **Modes:** `--mode debug` vs `--mode build` (by default each task uses its own mode, usually `debug`).
- **Prompt or tool changes:** run before and after your change with the same settings.
- **Variance:** `--repeat 3` runs each task three times. Model runs are not deterministic, so for small
  differences use repeats before concluding anything.

## Is compaction losing important information?

Two complementary checks, for when you change the summary prompt, the summariser model or the thresholds:

**1. Fidelity eval: what survives a summary?**

```bash
uv run codepilot bench compaction [--model <summariser id>] [--repeat 3]
```

It replays realistic sessions (`bench/compaction/*.json`: a debugging session and a feature-planning session)
containing planted key facts: your instructions and constraints, identifiers (file:line references, test
names, error values, ticket and trace ids), root causes and decisions, proposal outcomes, and next steps. It
runs the real `/compact` with your configured summariser, and reports which facts are kept, overall and by
kind. The report includes each summary so you can read it. It exits non-zero below 90%. Add a fixture by
writing a session and its facts (`"any"` or `"all"` substrings) in the same JSON shape.

**2. Stress test: does compaction hurt real work?**

```bash
uv run codepilot bench run --label normal
uv run codepilot bench run --context-tokens 30000 --label tight-window
uv run codepilot bench compare bench/results/*-normal/results.json bench/results/*-tight-window/results.json
```

A tiny pretend window forces pruning and summarising mid-task. If the pass rate holds, compaction isn't
losing what matters.

## Options (`codepilot bench run`)

| Option | Default | Meaning |
|---|---|---|
| `--tasks a,b` | all | Run only these task ids |
| `--tier` | `main` | Model tier: `auto`, `fast`, `main` or `hard` |
| `--mode` | per task | Force a mode for every task |
| `--repeat N` | 1 | Runs per task |
| `--jobs N` | 1 | Tasks in parallel (watch your provider's rate limits) |
| `--max-steps N` | 30 | Model↔tool round trips per task |
| `--timeout S` | 900 | Seconds per task before the agent is stopped |
| `--label NAME` | none | Name shown in reports and `compare` |
| `--prices FILE` | none | Per-token prices for cost estimates (copy `bench/prices.example.toml`) |
| `--keep` | off | Keep each task's working folder for inspection |
| `--context-tokens N` | per model | Pretend the context window is this small, to force compaction |
| `--prune-at`, `--compact-at` | from `.env` | Override the compaction thresholds for this run |
| `--out DIR` | `bench/results` | Where results go |

## How a task runs

1. `repo/` is copied to a fresh temporary folder and committed, so the diff is easy to see.
2. A throwaway session is created there (its own temporary `CODEPILOT_HOME`) in the task's mode.
3. The agent gets the prompt. Edits are **auto-applied**. Approvals are answered automatically:
   - `run_tests` and `run_checks`: approved
   - `run_command`: approved only for simple read/test commands (`python`, `pytest`, `uv`, `ls`, `cat`,
     `grep`, read-only `git`, ...); anything with `;`, `&&`, redirects or command substitution is refused
   - everything else (GitHub writes, opening other folders): refused
4. When the agent finishes (or hits `--max-steps`/`--timeout`), `hidden/` is copied in and `grade_cmd` runs.
   A task passes only if the hidden tests **and** the visible tests pass.

Commands run on your machine (in the temporary folder). The allowlist keeps the run safe for normal model
behaviour, but treat it like running any agent unattended: use a machine you're comfortable with.

## The tasks

| Task | Category | What's planted |
|---|---|---|
| `pagination-off-by-one` | failing test | Page offset and page-count rounding bugs |
| `price-filter-inverted` | bug report | Comparison inverted in a budget filter |
| `shared-cart-state` | bug report | Mutable default argument shared between instances |
| `token-expiry-timezones` | bug report (stack trace) | Naive vs timezone-aware datetime comparison |
| `money-rounding` | failing test | Float arithmetic for money (2.675 rounds to 2.67); needs Decimal with half-up rounding |
| `retry-returns-none` | bug report | Off-by-one in a retry loop swallows the final error |
| `cache-key-collision` | bug report | Cache key ignores currency |
| `agent-tool-output` | trace triage | An agent treats a JSON string tool result as a list; diagnose from `traces/` |
| `email-validation` | failing test | Over-permissive regex with `match` instead of `fullmatch` |
| `case-insensitive-sort` | bug report | Case-sensitive sort, missing tie-breaker |
| `page-size-config` | bug report (multi-file) | Wrong setting used as the default, no bounds checking |
| `path-traversal` | security | `../` escapes a public folder (including a prefix-matching trap) |
| `csv-export-feature` | feature | Implement a function from its docstring, with tests |

The hidden tests check the general fix, not just the reported symptom (for example the path-traversal
task includes a `public_backup/` sibling that defeats naive `startswith` checks).

## Adding a task

```
bench/tasks/<id>/
  task.toml        metadata and prompt
  repo/            the project the agent sees (include a root conftest.py for Python imports)
  hidden/          files copied in for grading, e.g. tests_hidden/test_hidden_<id>.py
  solution/repo/   files that fix the bug (overlaid on repo/ by `bench validate`)
```

`task.toml`:

```toml
id = "my-task"
title = "One-line summary"
category = "bug-report"          # failing-test | bug-report | trace-triage | security | feature | ...
difficulty = "medium"            # easy | medium | hard
mode = "debug"                   # default mode for this task
test_cmd = "python3 -m pytest -q"
grade_cmd = "python -m pytest -q -p no:cacheprovider tests_hidden tests"
prompt = """
What a user would actually say: the symptom, any stack trace or failing test, and what "fixed" means.
"""
```

Guidelines:
- Write the prompt like a real bug report. Don't name the fix.
- Hidden tests should accept any correct fix and reject plausible wrong ones.
- Give hidden test files unique names (`test_hidden_<id>.py`) so they don't clash with visible tests.
- Run `make bench-validate`: every task must fail unfixed and pass with its solution.

Tasks are Python because it's the most portable; any language works if `grade_cmd` can run it on the
benchmark machine.

## Using it in CI

`codepilot bench validate` needs no model and is safe for every CI run. Full runs cost money; run them on
demand or nightly against a fixed model, and keep the `results.json` files to track trends.
