# Troubleshooting

Start with `make doctor`. It tests each piece and prints the fix for most problems.

## Install

| Symptom | Fix |
|---|---|
| `uv: command not found` | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| uv fails with certificate or SSL errors, or `failed to resolve requirements from 'build-system.requires'` with a hint about `--system-certs` | Corporate TLS inspection. Update codepilot (`git pull`); the `make` commands now make uv trust the OS certificate store. Running uv directly: `uv sync --system-certs …` (older uv: `--native-tls`). Still failing: get the company CA file from IT and `export SSL_CERT_FILE=/path/to/ca.pem` |
| `requires-python >=3.11` | Install Python 3.11+ (`brew install python@3.12`); uv picks it up |
| `failed to download "<package>==<version>"` | Usually a company package mirror that doesn't have that release yet (many hold back new versions for a few weeks), or a proxy blocking `files.pythonhosted.org`. `make install` doesn't install the browser-test tools (Playwright, greenlet), so update codepilot first (`git pull`). If another package fails, ask for it to be allowed, or point uv at your mirror with `UV_INDEX_URL` |
| `The anthropic package isn't installed` | `uv sync --extra anthropic` (or `make install`) |
| `The openai package isn't installed` | `uv sync --extra openai` (or `make install`) |

## Amazon Bedrock

| Symptom | Cause and fix |
|---|---|
| `AWS SSO session missing or expired` | `aws sso login --profile <your-profile>` |
| `No AWS credentials` | Set `AWS_PROFILE` in `.env`, or configure credentials (`aws configure sso`) |
| `AccessDeniedException ... not authorized to perform bedrock:InvokeModelWithResponseStream` | Your role lacks the IAM permissions in [setup.md](setup.md#amazon-bedrock) |
| `AccessDeniedException ... don't have access to the model` | The model isn't enabled for your account/region, or the Anthropic use-case form hasn't been submitted (Bedrock console → Model catalog) |
| `ValidationException ... model identifier is invalid` / `on-demand throughput isn't supported` | Use an **inference profile** ID (e.g. `us.anthropic...`), not a bare model ID. `make doctor` lists valid ones |
| `ValidationException` mentioning caching | Handled automatically (caching turns off for that model). To force it off: `CODEPILOT_PROMPT_CACHE=0` |
| `ThrottlingException` after retries | You hit your account's tokens-per-minute quota. Wait, use a smaller tier, lower `--jobs` in bench, or request a quota increase |
| `TLS verification failed` / `CERTIFICATE_VERIFY_FAILED` | Keep `CODEPILOT_SYSTEM_CERTS=1`, or set `CODEPILOT_CA_BUNDLE` to your corporate CA file |
| Only Claude 4.5 models show up, though Claude 5.x is enabled | Update codepilot (`git pull && make install`). Claude 5.x on Bedrock uses the Messages API with `anthropic.claude-…` IDs, which older versions didn't use; run `uv run codepilot models --refresh` |
| A model you expect isn't in the dropdown | The dropdown only lists models that answered a test request. `uv run codepilot models --refresh` shows every model checked and why each one isn't usable (no access, pending onboarding, expired login). Once access is granted, use **Refresh model list** |
| A tier uses a newer model than `.env` says | By design: tiers use the newest enabled model in their family. Set `CODEPILOT_LATEST_MODELS=0` to pin the configured IDs |
| Your Claude 4.x models are missing and your role can't list inference profiles | codepilot then probes the known Claude 4.5/4.6 profile IDs for your region. If yours differs, set it in `CODEPILOT_MODEL_*`; it's always probed |
| `denied the request ... bedrock-mantle:CreateInference` | Add that IAM permission (see [setup.md](setup.md#amazon-bedrock)) |
| Every model is "not authorized" / 403, though your work account has access | codepilot is using a different AWS identity than you think: with no profile set it uses the default credential chain, which may be an old or personal login. `codepilot models` prints the identity it used. Set `AWS_PROFILE=<your-profile>` in `.env` (never commit `.env`), run `aws sso login --profile <your-profile>` if needed, then `codepilot models --refresh` |
| Works in the AWS CLI but not in codepilot | Check `AWS_PROFILE`/`AWS_REGION` in `.env` match what you use with the CLI; `make doctor` prints both |

## Anthropic API

| Symptom | Fix |
|---|---|
| `Anthropic API key missing or invalid` | Set `ANTHROPIC_API_KEY` in `.env`; check the key in the Console |
| `Model ... not found for this key` | Check `CODEPILOT_ANTHROPIC_MODEL_*`; `make doctor` lists your models |
| `rate limit hit` | Wait, or check your Console usage tier and limits |
| Billing or credit errors | Add credits or a payment method in the Console |
| `Couldn't reach the Anthropic API` | Network, proxy (`HTTPS_PROXY`) or TLS (`CODEPILOT_SYSTEM_CERTS=1`) |

## OpenAI API

| Symptom | Fix |
|---|---|
| `No OpenAI model configured` | Set `CODEPILOT_OPENAI_MODEL`; `make doctor` lists models your key can use |
| `OpenAI API key missing or invalid` | Set `OPENAI_API_KEY` |
| Errors about tools or `max_completion_tokens` on a compatible endpoint | The server doesn't implement those Chat Completions features; try another model or server |

## Ollama

| Symptom | Fix |
|---|---|
| `Cannot reach Ollama` | Start it: open the Ollama app, or `ollama serve` |
| `llama-server binary not found` (Intel Mac) | The Homebrew formula is broken on Intel: `brew uninstall ollama && brew install --cask ollama-app` |
| `model ... not found` | `ollama pull <model>` |
| Answers are wrong, or it prints tool calls as text | Small local models are weak at agent work. Fine for testing the app; use Claude for real work |

## The app

| Symptom | Fix |
|---|---|
| "Multimodal data provided, but model does not support…" or images ignored | The model can't read images (most small local models). Use a Claude or GPT-4o-class model, or a vision model on Ollama (e.g. `qwen2.5vl`) |
| The model says it can't see your screenshots | Attach them (paste, drop, or 🖼) or give their path in the message; both work for files outside the workspace, and big Retina screenshots are shrunk. If it still says so, run `uv run codepilot smoke --tier <tier>`: its "reads images" line shows whether that model accepts images |
| Ctrl+V doesn't paste on a Mac | ⌘V always works. Ctrl+V needs the browser's clipboard permission: allow it when asked. If it was blocked, codepilot shows a message: open `chrome://settings/content/clipboard` (Edge: `edge://settings/content/clipboard`) and add `http://127.0.0.1:8765` under Allowed. A work-managed browser may block this by policy; then only ⌘V works. Safari and Firefox show a small **Paste** button to click |
| A fix you pulled doesn't seem to take effect | The server keeps running the code it started with. `make restart` (or **Restart now** in the banner the app shows) loads the new code. `make start` also restarts a background server whose code changed |
| Not sure your Anthropic/OpenAI key setup works | `uv run codepilot smoke` runs a real end-to-end turn and reports each check |
| `address already in use` | Another codepilot is running, or something else uses the port: `codepilot status`; `codepilot stop` for a background one; otherwise `CODEPILOT_PORT=8766 make serve`, or stop the other one (`pkill -f "codepilot serve"`) |
| Page loads but nothing works | Hard-reload the browser (an old cached UI); check the log (`codepilot logs`, or the terminal where `make serve` runs) |
| The terminal fills with `HTTP Request: POST https://bedrock-…` or `Loading cached SSO token` | Older versions logged every request. Update (`git pull && make install`); set `CODEPILOT_VERBOSE=1` only when you want those lines |
| Codepilot.app is blocked by your company's security software | You don't need it: run `make start` once and close the terminal, then use a bookmark or Chrome's **Install page as app** ([details](setup.md#run-without-a-terminal)) |
| Codepilot.app opens nothing | See `~/.codepilot/launcher.log` and `codepilot logs`. If you moved the checkout or rebuilt `.venv`, run `codepilot app` again |
| From Codepilot.app, tests or `gh` aren't found, or the wrong AWS profile is used | The launcher imports your login shell's environment. Check that `zsh -ilc 'echo $PATH'` shows what you expect, or put the settings in `.env` |
| "At most 12 terminals can run at once" | Kill some from the Terminal menu (**Kill All Terminals**) |
| A terminal shows "Exited with code N" | The shell ended with an error; read the output, then press any key to close it or click **Restart** |
| `This session is already working` | A turn is still running in that session; wait or press Stop |
| `A tool call is waiting for approval` | Scroll the chat to the approval card and Approve or Deny |
| Terminal says "Refused: reload the page" | The server restarted, so the page's terminal token is stale (and its shells ended); reload the page |
| Terminal says "disabled" | `CODEPILOT_TERMINAL=0` is set |
| `github off` in the status bar | `gh auth login` (or `CODEPILOT_GITHUB=0` to hide it) |
| No test command detected | Set `CODEPILOT_TEST_CMD`, or tell codepilot in chat how to run the tests |
| No traces listed | Traces must be `.json`, `.jsonl`, `.ndjson`, `.log` or `.txt` in a `traces/`, `logs/`, `results/` or `eval_results/` folder, or in `CODEPILOT_TRACE_DIRS` |
| Apply says the file changed since the proposal | You (or a tool) edited the file after the proposal was made; ask codepilot to re-propose |
| Undo refused | The file changed after the change was applied; undo by hand or ask codepilot |
| Context meter near 100% | It clears old tool outputs at 60% and summarises at 80% automatically; click the meter (or `/compact`) to compact now; for a new topic, use Memory → Continue in new session |
| "no longer fits the model's context window" | codepilot compacts and retries once automatically. If it still fails, the current turn alone is too big (e.g. a huge pasted log): `/compact`, or continue in a new session |
| Context feels much smaller than in Claude Code or Kiro | Check the model: Claude 4.5 models (e.g. `claude-opus-4-5-…`) have 200k windows; Opus/Sonnet 4.6+ and 5.x have 1M. `make doctor` shows each tier's window and lists the newer inference profiles your account can use. Override with `CODEPILOT_CONTEXT_TOKENS` if needed |

## Getting more detail

The quickest way to report a problem is **Help (?) → Report a problem…** in the app's title bar:
- **Download report** saves a JSON file with what's needed to debug. It includes the code version, OS,
  settings (no keys), the session's state and (if ticked) its conversation, recent warnings and errors
  from the server and the page, and the server log. API keys, tokens, passwords, emails and your home path
  are removed.
- **Open GitHub issue** opens github.com/bbrennan/codepilot's new-issue page pre-filled with a short
  summary: your description, versions, the provider and mode, and error messages. It never includes the
  conversation or code, because the repository is public. Nothing is posted until you press Submit there,
  so review it first. Attach the downloaded report only if it contains nothing private.

Other sources:

- `make serve` logs to the terminal it runs in; a background server (`codepilot start`) logs to
  `~/.codepilot/server.log` (`codepilot logs -f`). `CODEPILOT_VERBOSE=1` adds every HTTP request.
- **Activity** (bottom panel) shows every model and tool call with inputs and outputs.
- Benchmark transcripts: `bench/results/<run>/transcripts/*.jsonl`.
- Open an issue with the `make doctor` output (it never prints secrets) and the relevant log lines.
