# Troubleshooting

Start with `make doctor`. It tests each piece and prints the fix for most problems.

## Install

| Symptom | Fix |
|---|---|
| `uv: command not found` | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| uv fails with certificate or SSL errors | Corporate TLS inspection: `export UV_NATIVE_TLS=1` and retry |
| `requires-python >=3.11` | Install Python 3.11+ (`brew install python@3.12`); uv picks it up |
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
| `address already in use` | Another codepilot is running, or something else uses the port: `CODEPILOT_PORT=8766 make serve`, or stop the other one (`pkill -f "codepilot serve"`) |
| Page loads but nothing works | Hard-reload the browser (an old cached UI); check the terminal where `make serve` runs for errors |
| `This session is already working` | A turn is still running in that session; wait or press Stop |
| `A tool call is waiting for approval` | Scroll the chat to the approval card and Approve or Deny |
| Terminal says "Refused: reload the page" | The server restarted, so the page's terminal token is stale; reload the page |
| Terminal says "disabled" | `CODEPILOT_TERMINAL=0` is set |
| `github off` in the status bar | `gh auth login` (or `CODEPILOT_GITHUB=0` to hide it) |
| No test command detected | Set `CODEPILOT_TEST_CMD`, or tell codepilot in chat how to run the tests |
| No traces listed | Traces must be `.json`, `.jsonl`, `.ndjson`, `.log` or `.txt` in a `traces/`, `logs/`, `results/` or `eval_results/` folder, or in `CODEPILOT_TRACE_DIRS` |
| Apply says the file changed since the proposal | You (or a tool) edited the file after the proposal was made; ask codepilot to re-propose |
| Undo refused | The file changed after the change was applied; undo by hand or ask codepilot |
| Context meter near 100% | It summarises automatically; for a new topic, start a new session |

## Getting more detail

- `make serve` logs to the terminal it runs in.
- **Activity** (bottom panel) shows every model and tool call with inputs and outputs.
- Benchmark transcripts: `bench/results/<run>/transcripts/*.jsonl`.
- Open an issue with the `make doctor` output (it never prints secrets) and the relevant log lines.
