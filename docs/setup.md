# Setup

This guide takes you from a fresh clone to a working codepilot, for each model provider. Budget 10 to 20
minutes the first time, most of it on cloud-account steps.

- [1. Prerequisites](#1-prerequisites)
- [2. Install](#2-install)
- [3. Choose a model provider](#3-choose-a-model-provider)
  - [Amazon Bedrock](#amazon-bedrock): Claude through your AWS account
  - [Anthropic API](#anthropic-api): Claude with your own Anthropic key
  - [OpenAI API](#openai-api): GPT models, or any OpenAI-compatible endpoint
  - [Ollama](#ollama): a free local model, for trying codepilot out
- [4. GitHub access (optional)](#github)
- [5. Optional analysers](#5-optional-analysers)
- [6. Verify with `make doctor`](#6-verify-with-make-doctor)
- [7. Start it](#7-start-it)
- [8. Updating](#8-updating)

---

## 1. Prerequisites

| Need | Why | Install |
|---|---|---|
| macOS or Linux | Built and tested on macOS. Linux should work; Windows via WSL2 is untested. | |
| Python **3.11+** | Runs codepilot | `brew install python@3.12` or [python.org](https://www.python.org/downloads/) |
| **uv** | Creates the virtual env and installs dependencies | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **git** | Cloning, diffs and the git tools the assistant uses | `xcode-select --install` (macOS) or your package manager |
| A modern browser | The UI | Chrome, Edge, Firefox or Safari |
| `make` | Shortcut commands (optional; every target is a plain command) | Preinstalled on macOS and most Linux |

Check them:

```bash
python3 --version   # 3.11 or newer
uv --version
git --version
```

## 2. Install

```bash
git clone https://github.com/bbrennan/codepilot.git
cd codepilot
cp .env.example .env      # your private settings; git-ignored
make install              # = uv sync --all-extras  (creates .venv)
```

`make install` installs everything, including the Anthropic and OpenAI SDKs. To install less:
`uv sync --extra dev` (Bedrock and Ollama only), and add `--extra anthropic` and/or `--extra openai` as
needed.

> **Behind a corporate proxy that inspects TLS?** If `uv` fails with certificate errors, run
> `export UV_NATIVE_TLS=1` first (it's also set in `.env.example`), so uv trusts your OS certificate store.

## 3. Choose a model provider

Set `CODEPILOT_PROVIDER` in `.env` to one of `bedrock`, `anthropic`, `openai`, `ollama`. You can switch at
any time; sessions are kept per machine, not per provider.

| Provider | Cost | Quality for coding | Where your code goes |
|---|---|---|---|
| `bedrock` | Pay per token on your AWS bill | Excellent (Claude) | Amazon Bedrock in your AWS account and region |
| `anthropic` | Pay per token on your Anthropic account | Excellent (Claude) | Anthropic, under your API account's terms |
| `openai` | Pay per token on your OpenAI account | Depends on the model | OpenAI (or the endpoint you configure) |
| `ollama` | Free | Weak with the small models a laptop can run | Stays on your machine |

> **Company code:** use the provider your employer has approved (often Bedrock in the company AWS account).
> A personal API key sends code to your personal account. Check your company's policy first.

---

### Amazon Bedrock

You need: an AWS account with Bedrock, permission to call Claude models, and AWS credentials on your
machine.

**Step 1: model access.** In the AWS console, open **Amazon Bedrock → Model catalog** in your region and
make sure the Anthropic Claude models you want are available. The first time an account uses Anthropic
models, Bedrock may ask for Anthropic's one-time use-case form. In company accounts the cloud team has
usually done this already.

**Step 2: IAM permissions.** Your role or user needs this, at minimum (attach it as an inline policy or ask
your cloud team):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeClaude",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": [
        "arn:aws:bedrock:*:*:inference-profile/*",
        "arn:aws:bedrock:*::foundation-model/anthropic.*"
      ]
    },
    {
      "Sid": "DiscoverModels",
      "Effect": "Allow",
      "Action": ["bedrock:ListInferenceProfiles", "bedrock:GetInferenceProfile", "bedrock:ListFoundationModels"],
      "Resource": "*"
    }
  ]
}
```

- codepilot calls the Converse streaming API, which is authorised by `bedrock:InvokeModelWithResponseStream`.
- Cross-region inference profiles (IDs starting `us.`, `eu.`, `apac.` or `global.`) route to several
  regions, so the foundation-model resource must allow every region in the profile, hence the `*`.
- Optional, only if you set `CODEPILOT_LOG_GROUPS`: `logs:FilterLogEvents` on those log groups.

**Step 3: credentials.** codepilot uses the standard AWS credential chain (the same as the AWS CLI). The
recommended option is an IAM Identity Center (SSO) profile:

```bash
aws configure sso                       # once: SSO start URL, region, account, role, profile name
aws sso login --profile your-profile    # each day, or whenever the session expires
```

Then in `.env`:

```bash
CODEPILOT_PROVIDER=bedrock
AWS_PROFILE=your-profile
AWS_REGION=us-east-1                    # where your models are enabled
```

Other credential sources also work: `aws configure` access keys (avoid long-lived keys where you can),
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN` environment variables, or an instance or
container role.

**Step 4: model IDs.** Set the three tiers to inference-profile IDs your account can use:

```bash
CODEPILOT_MODEL_FAST=us.anthropic.claude-haiku-4-5-20251001-v1:0
CODEPILOT_MODEL_MAIN=us.anthropic.claude-sonnet-4-5-20250929-v1:0
CODEPILOT_MODEL_HARD=us.anthropic.claude-opus-4-5-20251101-v1:0
```

Not sure which IDs you have? Run `make doctor`. If a model call fails, it lists every Anthropic inference
profile visible to your account in that region. Newer Claude generations may be available; use them if
they are.

**Network notes**
- **Corporate TLS inspection:** `CODEPILOT_SYSTEM_CERTS=1` (default) verifies AWS certificates against your
  OS trust store, which already trusts the corporate root CA. Or set `CODEPILOT_CA_BUNDLE=/path/to/ca.pem`.
- **Proxy:** set `HTTPS_PROXY` if your network requires one.
- **PrivateLink/VPC endpoint:** `CODEPILOT_BEDROCK_ENDPOINT_URL=https://...`.

---

### Anthropic API

You need: an Anthropic Console account with billing set up, and an API key.

1. Sign in at **https://console.anthropic.com/** and add a payment method or credits (**Settings → Billing**).
2. Create a key under **API keys**. Copy it once; it isn't shown again.
3. In `.env`:

```bash
CODEPILOT_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...            # stays in .env, which git ignores
```

Defaults: `fast=claude-haiku-5-5`, `main=claude-sonnet-5-5`, `hard=claude-opus-5-5`, effort `high`. To
change them: `CODEPILOT_ANTHROPIC_MODEL_FAST/MAIN/HARD` (or `CODEPILOT_ANTHROPIC_MODEL` for all tiers) and
`CODEPILOT_EFFORT` (`low`, `medium`, `high`, `xhigh` or `max`; higher means more thorough but slower and
costlier).

What codepilot does with the Anthropic API, so you aren't surprised:
- **Adaptive thinking** is on (it can't be switched off on the newest models). Reasoning is kept and replayed
  unchanged, as the API requires.
- **Prompt caching** is on: repeated context is billed at the much lower cache-read rate.
- **Refusal fallbacks** are on for Opus and Sonnet 5.5 (`fallbacks: "default"`). If the model declines a
  request on safety grounds, the API reruns it on Anthropic's designated fallback model within the same call.
- Uses the `anthropic` SDK; `ANTHROPIC_BASE_URL`/`CODEPILOT_ANTHROPIC_BASE_URL` work for gateways.

---

### OpenAI API

You need: an OpenAI Platform account with billing and an API key.

1. Sign in at **https://platform.openai.com/**, set up billing, and create a key at
   **https://platform.openai.com/api-keys**.
2. In `.env`:

```bash
CODEPILOT_PROVIDER=openai
OPENAI_API_KEY=sk-...
CODEPILOT_OPENAI_MODEL=<model id>       # required; see below
```

There's no default OpenAI model, because the model lineup changes often. Run `make doctor`: with the key
set, it lists every model your key can use. Pick one that supports tool (function) calling. Optional:
per-tier `CODEPILOT_OPENAI_MODEL_FAST/MAIN/HARD`, and `CODEPILOT_EFFORT=low|medium|high` for reasoning models.

**OpenAI-compatible endpoints** (LiteLLM, OpenRouter, vLLM, Azure OpenAI's v1 API, and others): set
`CODEPILOT_OPENAI_BASE_URL` to the endpoint and `OPENAI_API_KEY` to its key. codepilot uses the Chat
Completions API with function tools, which most compatible servers implement.

---

### Ollama

Free and local. Good for trying codepilot without an account; small local models are not good enough for
real reviews or fixes.

```bash
make ollama        # installs the Ollama app (macOS, via Homebrew cask) and pulls llama3.2:3b (~2 GB)
make demo          # runs codepilot on Ollama against the bundled demo project
```

Manual install: download from https://ollama.com, then `ollama pull <model>`. Note that the Homebrew
**formula** (`brew install ollama`) lacks the model runner on Intel Macs; use the app or the cask
(`brew install --cask ollama-app`).

In `.env`: `CODEPILOT_PROVIDER=ollama` and `CODEPILOT_OLLAMA_MODEL=<model>`. Rough sizing: 3B models on 8
to 16 GB without a GPU; 7 to 8B models (e.g. `qwen2.5-coder:7b`) on 16 GB; 30B-class coding models need
Apple Silicon with 32 GB+ or a GPU.

---

<a id="github"></a>
## 4. GitHub (optional)

Lets the assistant read pull requests, review comments, issues, CI runs and failed-job logs, and (with
your approval) comment or open PRs. It uses the official GitHub CLI and its existing login; codepilot never
handles a token.

```bash
brew install gh                    # or see https://cli.github.com
gh auth login                      # github.com: choose HTTPS and browser login
gh auth status                     # check
```

- **GitHub Enterprise Server:** `gh auth login --hostname github.example.com`, then
  `CODEPILOT_GH_HOST=github.example.com` in `.env`.
- **Scopes:** the default `gh` login (`repo`, `read:org`) is enough. Re-running CI also needs `workflow`
  (`gh auth refresh -s workflow`).
- **Turn it off:** `CODEPILOT_GITHUB=0`.
- **Reusing Copilot's or Kiro's login:** not possible. VS Code keeps Copilot's GitHub token in its own
  secure storage for its own app, and Kiro's sign-in is for Kiro's service. The `gh` login is what
  terminal tools share.

## 5. Optional analysers

codepilot runs whichever of these it finds (in the workspace's `.venv` or `node_modules`, or on your
PATH) and feeds their output to the model. Nothing is required.

```bash
brew install ripgrep gitleaks          # fast search; secret scanning
uv tool install ruff                   # Python lint
uv tool install pyright                # or: uv tool install mypy (Python types)
uv tool install bandit                 # Python security lint
brew install semgrep                   # multi-language security rules (registry rules need network)
# JS/TS projects: eslint and typescript from the project's own node_modules are used automatically.
```

## 6. Verify with `make doctor`

```bash
make doctor
```

It checks, depending on the provider:
- **Bedrock:** the AWS profile and region, the TLS mode, your identity (`sts:GetCallerIdentity`), then one
  tiny call per model tier. If a call fails, it lists the inference profiles you can use.
- **Anthropic or OpenAI:** that the key is set (value hidden), the models your key can see, then one tiny
  call per tier.
- **Ollama:** the server is up, the models are pulled, and a generation works.
- **GitHub:** who `gh` is logged in as.
- **Workspace** (if `CODEPILOT_REPO` is set): the test command, the eval command, and trace folders.

Each check prints `ok`, `warn` or `FAIL` with the fix. See [troubleshooting.md](troubleshooting.md) for
the common failures.

## 7. Start it

```bash
make serve           # opens http://127.0.0.1:8765
```

Then click **Open folder…**, or just tell it in chat: "review ~/code/my-service". The
[usage guide](usage.md) covers everything from there.

## 8. Updating

```bash
git pull
make install
make test            # optional: codepilot's own tests, no cloud access needed
```

Your sessions, notes and settings live outside the repo (`~/.codepilot`, `.env`) and survive updates.
