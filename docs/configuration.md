# Configuration reference

codepilot is configured only through environment variables. At startup it loads the first `.env` it finds:
`$CODEPILOT_ENV_FILE` (or `codepilot --env-file PATH`), then `./.env`, then the `.env` in the codepilot
checkout. Variables already set in your shell take precedence over the file. Values may be quoted, and
lines may start with `export`.

Run `make doctor` after any change.

## Provider and models

| Variable | Default | Description |
|---|---|---|
| `CODEPILOT_PROVIDER` | `bedrock` | `bedrock`, `anthropic`, `openai` or `ollama` |
| `CODEPILOT_DEFAULT_TIER` | `auto` | Tier for new sessions: `auto` (picks per turn; see [usage](usage.md#model-tiers-and-cost)), `fast`, `main` or `hard` |
| `CODEPILOT_MAX_TOKENS` | `16000` | Max output tokens per model reply (Ollama is capped at 8192) |
| `CODEPILOT_MAX_STEPS` | `40` | Max model↔tool round trips per message; the assistant asks to continue after that |
| `CODEPILOT_CONTEXT_TOKENS` | per model | Context window override. Defaults by model: 1M for Claude 4.6+ and 5.x (Bedrock and Anthropic API), 200k for Claude 4.5 and older, 128k for OpenAI, `CODEPILOT_OLLAMA_NUM_CTX` for Ollama. `make doctor` shows each tier's window |
| `CODEPILOT_PRUNE_AT` | `0.6` | Fraction of the prompt budget (window minus reply reserve) at which old tool outputs are cleared |
| `CODEPILOT_COMPACT_AT` | `0.8` | Fraction at which earlier turns are summarised |

### Amazon Bedrock (`CODEPILOT_PROVIDER=bedrock`)

| Variable | Default | Description |
|---|---|---|
| `AWS_PROFILE` / `CODEPILOT_AWS_PROFILE` | none (default chain) | AWS profile to use (e.g. your SSO profile) |
| `AWS_REGION` / `CODEPILOT_REGION` / `AWS_DEFAULT_REGION` | `us-east-1` | Bedrock region |
| `CODEPILOT_MODEL_FAST` | `anthropic.claude-haiku-5-5` | Fast tier. `anthropic.*` IDs use the Messages API; `us./eu./global.anthropic…` profile IDs use Converse |
| `CODEPILOT_MODEL_MAIN` | `anthropic.claude-sonnet-5-5` | Main tier |
| `CODEPILOT_MODEL_HARD` | `anthropic.claude-opus-5-5` | Hard tier |
| `CODEPILOT_LATEST_MODELS` | `1` | Each tier uses the newest enabled model in its configured model's family (Sonnet 4.6 when the tier says Sonnet 4.5). `0` uses exactly the configured IDs, and Auto uses them too |
| `CODEPILOT_BEDROCK_API` | `auto` | `auto` (by model ID), `messages` or `converse` |
| `CODEPILOT_BEDROCK_MESSAGES_URL` | SDK default | Custom endpoint for the Bedrock Messages API |
| `CODEPILOT_PROMPT_CACHE` | `1` | Bedrock prompt caching; switches itself off if a model rejects it |
| `CODEPILOT_THINKING` | `off` | `off`, `adaptive` (Claude 4.6+), or a thinking budget such as `4000` (Claude 4.5) |
| `CODEPILOT_BEDROCK_ENDPOINT_URL` | none | Custom bedrock-runtime endpoint (VPC/PrivateLink) |

`REVIEWER_MODEL_SCAN/FIX/HARD` and `REVIEWER_TARGET_REPO` are accepted as fallbacks for the three model
tiers and the default repo, for compatibility with an older internal tool.

### Anthropic API (`CODEPILOT_PROVIDER=anthropic`)

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Your key, read by the official SDK. Keep it in `.env` only |
| `CODEPILOT_ANTHROPIC_MODEL` | none | Model for all tiers (overrides the defaults below) |
| `CODEPILOT_ANTHROPIC_MODEL_FAST` | `claude-haiku-5-5` | Fast tier |
| `CODEPILOT_ANTHROPIC_MODEL_MAIN` | `claude-sonnet-5-5` | Main tier |
| `CODEPILOT_ANTHROPIC_MODEL_HARD` | `claude-opus-5-5` | Hard tier |
| `CODEPILOT_EFFORT` | `high` | `low`, `medium`, `high`, `xhigh` or `max`; how thoroughly the model works (also applies to Claude 5.x on Bedrock) |
| `CODEPILOT_ANTHROPIC_BASE_URL` (or `ANTHROPIC_BASE_URL`) | API default | Gateway or proxy URL |

### OpenAI API (`CODEPILOT_PROVIDER=openai`)

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | required | Your key, read by the official SDK |
| `CODEPILOT_OPENAI_MODEL` | **required** | Model for all tiers; `make doctor` lists what your key can use |
| `CODEPILOT_OPENAI_MODEL_FAST` / `_MAIN` / `_HARD` | `CODEPILOT_OPENAI_MODEL` | Per-tier overrides |
| `CODEPILOT_EFFORT` | none | `low`, `medium` or `high`, sent as `reasoning_effort` (reasoning models only) |
| `CODEPILOT_OPENAI_BASE_URL` (or `OPENAI_BASE_URL`) | API default | Any OpenAI-compatible endpoint |

### Ollama (`CODEPILOT_PROVIDER=ollama`)

| Variable | Default | Description |
|---|---|---|
| `CODEPILOT_OLLAMA_URL` / `OLLAMA_HOST` | `http://localhost:11434` | Ollama server |
| `CODEPILOT_OLLAMA_MODEL` | `llama3.2:3b` | Model for all tiers |
| `CODEPILOT_OLLAMA_MODEL_FAST` / `_MAIN` / `_HARD` | `CODEPILOT_OLLAMA_MODEL` | Per-tier overrides |
| `CODEPILOT_OLLAMA_NUM_CTX` | `32768` | Context size requested from Ollama (and codepilot's budget for it) |

## Network

| Variable | Default | Description |
|---|---|---|
| `CODEPILOT_SYSTEM_CERTS` | `1` | Verify TLS with the OS trust store (works behind TLS-inspecting proxies) |
| `CODEPILOT_CA_BUNDLE` / `AWS_CA_BUNDLE` | none | Use this CA bundle file instead (Bedrock) |
| `HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY` | none | Standard proxy settings, honoured by all providers |
| `UV_NATIVE_TLS` | none | For `uv` installs behind TLS inspection (not used by codepilot itself) |

## Workspace

| Variable | Default | Description |
|---|---|---|
| `CODEPILOT_REPO` | none | Folder pre-filled for new sessions and `codepilot chat` |
| `CODEPILOT_TEST_CMD` | detected | Test command. Detection: `uv run pytest -q` (if `uv.lock`), `python3 -m pytest -q`, `npm test --silent`, `go test ./...`, `cargo test`, or `make test` |
| `CODEPILOT_EVAL_CMD` | none | Command that regenerates traces (e.g. an eval run). A hint for the assistant; always needs approval |
| `CODEPILOT_TRACE_DIRS` | auto | Extra trace/log folders, comma-separated (relative or absolute). Auto: `traces/`, `logs/`, `eval_results/`, `results/`, `journeys/` near the root |
| `CODEPILOT_LOG_GROUPS` | none | CloudWatch log groups the assistant may search, read-only; a trailing `*` matches a prefix |
| `CODEPILOT_SKILL_DIRS` | none | Extra skill folders, comma-separated (e.g. `~/.claude/skills`) |

## GitHub

| Variable | Default | Description |
|---|---|---|
| `CODEPILOT_GITHUB` | `1` | Enable the `github` tool (needs `gh` installed and logged in) |
| `CODEPILOT_WEB` | `1` | Built-in web tools: `library_docs` (Context7) and `web_fetch` (asks per site); `0` turns them off |
| `BRAVE_API_KEY` | unset | Adds the `web_search` tool (Brave Search API; free tier available) |
| `CONTEXT7_API_KEY` | unset | Higher rate limits for `library_docs` (works without a key) |
| `CODEPILOT_GH_HOST` / `GH_HOST` | `github.com` | GitHub Enterprise Server host |

## Behaviour and safety

| Variable | Default | Description |
|---|---|---|
| `CODEPILOT_AUTO_APPROVE_TESTS` | `0` | Run tests and analyser checks without asking (other commands always ask) |
| `CODEPILOT_AUTO_APPLY` | `0` | Write proposed edits immediately; each can still be undone |
| `CODEPILOT_VERIFY` | `1` | Verification receipts: test pending changes on a copy of the workspace before review (the **Verify** button, the `verify_changes` tool, and an automatic run when auto-run tests is on). `0` turns it all off |
| `CODEPILOT_VERIFY_TIMEOUT` | `600` | Seconds a verification may take in total (tests plus analysers) |
| `CODEPILOT_TERMINAL` | `1` | Enable terminals (local shells; see [security.md](security.md#the-terminal)) |

## App

| Variable | Default | Description |
|---|---|---|
| `CODEPILOT_HOME` | `~/.codepilot` | Sessions database, notes, scratch files, custom skills and modes |
| `CODEPILOT_HOST` | `127.0.0.1` | Bind address. Keep it on localhost (see [security.md](security.md)) |
| `CODEPILOT_PORT` | `8765` | UI port |
| `CODEPILOT_ENV_FILE` | `./.env` | Load settings from another file |
| `CODEPILOT_VERBOSE` | unset | `1` logs every HTTP request and credential lookup made by the AWS/Anthropic/OpenAI libraries |
| `CODEPILOT_APP_BROWSER` | auto | Browser for `codepilot start`'s app window, e.g. `Google Chrome`, `Microsoft Edge`, `Brave Browser` |

## Files codepilot reads and writes

| Path | What |
|---|---|
| `.env` | Your settings and keys (git-ignored) |
| `~/.codepilot/codepilot.db` | Sessions, messages, proposals, token usage (SQLite) |
| `~/.codepilot/models.json` | Which models your account can use (cached 12h; `codepilot models --refresh`) |
| `~/.codepilot/server.pid`, `server.log`, `launcher.log` | The background server started by `codepilot start` or Codepilot.app |
| `~/Applications/Codepilot.app` | The macOS launcher written by `codepilot app` |
| `~/.codepilot/notes/<folder>-<hash>.md` | Per-workspace notes |
| `~/.codepilot/scratch/<session>/` | The assistant's throwaway repro scripts |
| `~/.codepilot/verify/<session>/` | Temporary copies of the workspace while pending changes are verified (removed afterwards, and at start) |
| `~/.codepilot/images/` | Copies of images in conversations, for display (safe to delete) |
| `~/.codepilot/trash/` | Files and folders you deleted from the Explorer (restorable; delete old ones by hand) |
| `~/.codepilot/skills/`, `~/.codepilot/modes/` | Your custom skills and modes |
| `~/.codepilot/steering/*.md` | Your steering docs for every workspace ([steering.md](steering.md)) |
| `~/.codepilot/AGENTS.md` | Global instructions applied to every workspace (always on) |
| `<workspace>/.codepilot/steering/*.md` | The workspace's steering docs (commit them) |
| `<workspace>/.codepilot/specs/<name>/` | Specs: `requirements.md`/`bugfix.md`, `design.md`, `tasks.md`, `spec.json` ([specs.md](specs.md)) |
| `<workspace>/.codepilot/modes/`, `.agents/skills/`, `.claude/skills/` | Project-specific modes and skills |
