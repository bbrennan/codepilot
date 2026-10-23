# codepilot

A local, IDE-style coding assistant that runs in your browser and works on any folder on your machine.
Point it at a codebase and ask it, in chat, to review code, find and fix bugs, build features, write tests,
explain how things work, or work out why a run failed from its traces and logs.

It runs on **Claude via Amazon Bedrock**, **Claude via the Anthropic API**, **OpenAI** (or any
OpenAI-compatible endpoint), or a free **local model via Ollama**.

```
┌ codepilot ── my-service ── ⌘P ───────────────────────────────────────────────────────────────┐
│ ▤ │ EXPLORER          │ invoice.py ✕  trace: checkout.json ✕  #3 diff ✕ │ Debug ▾  main ▾      │
│ ⌕ │ ▾ src             │  12  def line_total(price, qty, discount=0):     │ ▸ run_tests  ✓ 2.1s  │
│ ∿ │   ▸ billing       │  13      raw = Decimal(str(price)) * qty ...     │ ▸ read_file  ✓       │
│ ⑂ │   ▸ api           │                                                  │ Root cause: float    │
│ ◫ │ ▸ tests           ├──────────────────────────────────────────────────┤ math in line_total…  │
│   │                   │ ACTIVITY  OUTPUT                                 │ [Apply] [Reject]     │
└ bedrock · us-east-1 · main ─ ⑂ main ─ pytest ─ github: you ─ context 12% ─ 48k tokens ───────┘
```

## What it does

- **Works like an IDE:** file explorer, tabs with syntax highlighting, search, a ⌘P file palette, git
  changes, an integrated terminal, and chat docked on the right. Reference code with `@file` or `@file:10-40`, drag files in, or
  select lines and **Add to chat**.
- **Safe by default:** it reads freely, but every edit is a diff you **Apply** (and can **Undo**), and every
  shell command needs your approval. It never commits or pushes.
- **Focused modes:** Ask, Plan, Build, Debug, Bug-hunt and Review, each a focused agent. Add your own.
- **Built for debugging:** it reproduces first (a failing test or a scratch script), tests hypotheses one at
  a time, fixes the root cause, and adds a regression test. Skills such as `diagnose-bug`, `tdd`,
  `code-review` and `security-review` are built in, and community `SKILL.md` skills work too.
- **Sees run time, not just code:** a trace viewer with span timelines for JSON/JSONL traces (AgentCore,
  OpenTelemetry, structured logs), plus optional CloudWatch Logs search.
- **Uses real tools:** linters, type checkers and security scanners (ruff, mypy/pyright, eslint/tsc,
  gitleaks, semgrep, ...) when installed; ripgrep for search; GitHub PRs, issues and CI logs through `gh`.
- **Remembers:** full session history, an automatic rolling summary for long sessions, and per-folder notes.
  It follows `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, Kiro steering and Copilot instruction files.
- **Measurable:** `codepilot bench` grades it on planted-bug tasks with hidden tests, so you can compare
  models and changes.

## Quick start

You need macOS or Linux, Python 3.11+, [uv](https://docs.astral.sh/uv/) and git.

```bash
git clone https://github.com/bbrennan/codepilot.git && cd codepilot
cp .env.example .env
make install
```

Then configure **one** provider in `.env`. Full details for each, including accounts, permissions and keys,
are in **[docs/setup.md](docs/setup.md)**.

<details open><summary><b>Amazon Bedrock</b> (Claude through your AWS account)</summary>

```bash
# .env
CODEPILOT_PROVIDER=bedrock
AWS_PROFILE=your-sso-profile
AWS_REGION=us-east-1
```
```bash
aws sso login --profile your-sso-profile
```
Needs Claude model access in Bedrock and `bedrock:InvokeModelWithResponseStream` permission
([details](docs/setup.md#amazon-bedrock)).
</details>

<details><summary><b>Anthropic API</b> (your own key)</summary>

```bash
# .env
CODEPILOT_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```
Create a key at console.anthropic.com ([details](docs/setup.md#anthropic-api)).
</details>

<details><summary><b>OpenAI</b> (your own key, or a compatible endpoint)</summary>

```bash
# .env
CODEPILOT_PROVIDER=openai
OPENAI_API_KEY=sk-...
CODEPILOT_OPENAI_MODEL=<a model id>      # `make doctor` lists yours
```
([details](docs/setup.md#openai-api))
</details>

<details><summary><b>Ollama</b> (free and local; for trying it out)</summary>

```bash
make ollama     # install Ollama and pull a small model
make demo       # run codepilot on the bundled demo project
```
([details](docs/setup.md#ollama))
</details>

Then:

```bash
make doctor     # checks credentials, models, GitHub and tools, and tells you how to fix anything
make serve      # opens http://127.0.0.1:8765
```

Click **Open folder…** (or say "review ~/code/my-service" in chat) and go. See
**[docs/usage.md](docs/usage.md)**.

## Documentation

| Doc | What's in it |
|---|---|
| [Setup](docs/setup.md) | Prerequisites, install, every provider (accounts, IAM, keys), GitHub, analysers, `make doctor` |
| [Usage](docs/usage.md) | The UI, modes, approvals, Apply/Undo, workflows, traces, GitHub, memory, shortcuts, tips |
| [Configuration](docs/configuration.md) | Every environment variable, and where files are stored |
| [Skills and modes](docs/skills-and-modes.md) | Built-in skills, installing and writing skills, custom modes |
| [Benchmark](docs/benchmark.md) | Running, comparing and extending the planted-bug benchmark |
| [Security](docs/security.md) | Where your code goes, what's stored, what the assistant can and can't do |
| [Troubleshooting](docs/troubleshooting.md) | Symptom → fix tables for every provider and the app |
| [Architecture](docs/architecture.md) | How it works, and how to add tools, providers, modes and tasks |
| [Contributing](CONTRIBUTING.md) | Dev setup, tests, conventions |

## Commands

| Command | What it does |
|---|---|
| `make install` | Install or update dependencies (`uv sync --all-extras`) |
| `make doctor` | Check your setup |
| `make serve` | Start the UI |
| `make chat` | Terminal chat instead of the browser |
| `make test` | codepilot's own tests (no cloud access needed) |
| `make bench` / `make bench-validate` | Run or validate the benchmark |
| `make ollama` / `make demo` | Local model setup and demo |

## Status

Early and actively developed. The app has been run end to end with Ollama. The Bedrock, Anthropic and
OpenAI providers are covered by automated tests against faked SDK clients, so run `make doctor` to confirm
yours works before relying on it. Please report rough edges.

## License

[MIT](LICENSE). Bundled third-party components keep their own licences; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
