"""Settings. Everything comes from environment variables, optionally loaded from a .env file.

See .env.example for the full list. Nothing about the AWS account, region or models is hard-coded
beyond fallback defaults, so a fresh clone is configured entirely through .env.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

TIERS = ("fast", "main", "hard")
PROVIDERS = ("bedrock", "anthropic", "openai", "ollama")

# Fallbacks only; set CODEPILOT_MODEL_* in .env for your account.
DEFAULT_MODELS = {
    # Claude 5.x on Bedrock is served by the Messages API (bedrock-mantle) with anthropic.* IDs. Older
    # inference-profile IDs (us./eu./global.anthropic...) still work and go through the Converse API.
    "bedrock": {
        "fast": "anthropic.claude-haiku-5-5",
        "main": "anthropic.claude-sonnet-5-5",
        "hard": "anthropic.claude-opus-5-5",
    },
    "anthropic": {"fast": "claude-haiku-5-5", "main": "claude-sonnet-5-5", "hard": "claude-opus-5-5"},
    "openai": {"fast": "", "main": "", "hard": ""},  # set CODEPILOT_OPENAI_MODEL; `codepilot doctor` lists yours
    "ollama": {"fast": "llama3.2:3b", "main": "llama3.2:3b", "hard": "llama3.2:3b"},
}

# The reviewer tool's env names, honoured as fallbacks so one .env can serve both.
_REVIEWER_MODEL_VARS = {"fast": "REVIEWER_MODEL_SCAN", "main": "REVIEWER_MODEL_FIX", "hard": "REVIEWER_MODEL_HARD"}

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def load_env_file(path: str | Path | None = None) -> Path | None:
    """Load KEY=VALUE lines (optionally prefixed with `export`) without overriding the real environment.

    Looks at $CODEPILOT_ENV_FILE, then ./.env, then the .env next to this package's checkout.
    """
    candidates = [path] if path else [
        os.environ.get("CODEPILOT_ENV_FILE"),
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for cand in candidates:
        if not cand:
            continue
        p = Path(cand).expanduser()
        if not p.is_file():
            continue
        for raw in p.read_text().splitlines():
            if raw.lstrip().startswith("#"):
                continue
            m = _ENV_LINE.match(raw)
            if not m:
                continue
            key, value = m.group(1), m.group(2).strip()
            if value and value[0] in "\"'":
                try:
                    value = shlex.split(value)[0] if value else ""
                except ValueError:
                    value = value.strip("\"'")
            else:
                value = value.split(" #", 1)[0].strip()
            os.environ.setdefault(key, os.path.expandvars(value))
        return p
    return None


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value not in (None, ""):
            return value
    return default


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    provider: str
    # Bedrock
    region: str
    profile: str | None
    endpoint_url: str | None
    bedrock_api: str  # auto | converse | messages
    bedrock_messages_url: str | None
    ca_bundle: str | None
    system_certs: bool
    prompt_cache: bool
    thinking: str  # "off", "adaptive", or an integer thinking budget
    effort: str  # "", low, medium, high, xhigh, max (Anthropic API / OpenAI reasoning effort)
    # Direct APIs (keys come from ANTHROPIC_API_KEY / OPENAI_API_KEY, read by the official SDKs)
    anthropic_base_url: str | None
    openai_base_url: str | None
    # Ollama
    ollama_url: str
    # Models / generation
    models: dict[str, str]
    default_tier: str
    max_tokens: int
    # Target repo
    default_repo: str | None
    test_cmd: str  # "" = detect per repo
    eval_cmd: str  # optional hint, run via run_command
    trace_dirs: list[str]
    log_groups: list[str]
    auto_approve_tests: bool
    auto_apply_edits: bool
    terminal: bool
    # GitHub (via the gh CLI and its own login)
    github: bool
    github_host: str | None
    # App
    home: Path
    context_tokens: int | None  # explicit window override; else per model (see context_window)
    prune_at: float  # fraction of the prompt budget at which old tool outputs are cleared
    compact_at: float  # fraction at which earlier turns are summarised
    ollama_num_ctx: int
    max_steps: int
    host: str
    port: int

    @classmethod
    def from_env(cls) -> Config:
        provider = _env("CODEPILOT_PROVIDER", default="bedrock").lower()
        if provider not in PROVIDERS:
            raise ValueError(f"CODEPILOT_PROVIDER must be one of {PROVIDERS}, got {provider!r}")
        if provider == "bedrock":
            models = {t: _env(f"CODEPILOT_MODEL_{t.upper()}", _REVIEWER_MODEL_VARS[t],
                              default=DEFAULT_MODELS["bedrock"][t]) for t in TIERS}
        else:
            prefix = f"CODEPILOT_{provider.upper()}_MODEL"
            base = _env(prefix)
            models = {t: _env(f"{prefix}_{t.upper()}", default=base or DEFAULT_MODELS[provider][t]) for t in TIERS}
        default_tier = _env("CODEPILOT_DEFAULT_TIER", default="main")
        if default_tier not in TIERS:
            raise ValueError(f"CODEPILOT_DEFAULT_TIER must be one of {TIERS}, got {default_tier!r}")
        return cls(
            provider=provider,
            region=_env("CODEPILOT_REGION", "AWS_REGION", "AWS_DEFAULT_REGION", default="us-east-1"),
            profile=_env("CODEPILOT_AWS_PROFILE", "AWS_PROFILE"),
            endpoint_url=_env("CODEPILOT_BEDROCK_ENDPOINT_URL"),
            bedrock_api=_env("CODEPILOT_BEDROCK_API", default="auto").lower(),
            bedrock_messages_url=_env("CODEPILOT_BEDROCK_MESSAGES_URL"),
            ca_bundle=_env("CODEPILOT_CA_BUNDLE", "AWS_CA_BUNDLE"),
            system_certs=_flag("CODEPILOT_SYSTEM_CERTS", True),
            prompt_cache=_flag("CODEPILOT_PROMPT_CACHE", True),
            thinking=_env("CODEPILOT_THINKING", default="off").strip().lower(),
            effort=_env("CODEPILOT_EFFORT",
                        default="high" if provider in ("anthropic", "bedrock") else "").strip().lower(),
            anthropic_base_url=_env("CODEPILOT_ANTHROPIC_BASE_URL"),
            openai_base_url=_env("CODEPILOT_OPENAI_BASE_URL"),
            ollama_url=_env("CODEPILOT_OLLAMA_URL", "OLLAMA_HOST", default="http://localhost:11434").rstrip("/"),
            models=models,
            default_tier=default_tier,
            max_tokens=int(_env("CODEPILOT_MAX_TOKENS", default="16000")),
            default_repo=_env("CODEPILOT_REPO", "REVIEWER_TARGET_REPO"),
            test_cmd=_env("CODEPILOT_TEST_CMD", default=""),
            eval_cmd=_env("CODEPILOT_EVAL_CMD", default=""),
            trace_dirs=_list("CODEPILOT_TRACE_DIRS"),
            log_groups=_list("CODEPILOT_LOG_GROUPS"),
            auto_approve_tests=_flag("CODEPILOT_AUTO_APPROVE_TESTS", False),
            auto_apply_edits=_flag("CODEPILOT_AUTO_APPLY", False),
            terminal=_flag("CODEPILOT_TERMINAL", True),
            github=_flag("CODEPILOT_GITHUB", True),
            github_host=_env("CODEPILOT_GH_HOST", "GH_HOST"),
            home=Path(_env("CODEPILOT_HOME", default="~/.codepilot")).expanduser(),
            context_tokens=int(_env("CODEPILOT_CONTEXT_TOKENS", default="0")) or None,
            prune_at=float(_env("CODEPILOT_PRUNE_AT", default="0.6")),
            compact_at=float(_env("CODEPILOT_COMPACT_AT", default="0.8")),
            ollama_num_ctx=int(_env("CODEPILOT_OLLAMA_NUM_CTX", default="32768")),
            max_steps=int(_env("CODEPILOT_MAX_STEPS", default="40")),
            host=_env("CODEPILOT_HOST", default="127.0.0.1"),
            port=int(_env("CODEPILOT_PORT", default="8765")),
        )

    def context_window(self, model: str) -> int:
        """Context window in tokens for a model. CODEPILOT_CONTEXT_TOKENS overrides the defaults."""
        if self.context_tokens:
            return self.context_tokens
        if self.provider == "ollama":
            return self.ollama_num_ctx
        if self.provider == "openai":
            return 128_000
        m = model.lower()
        long_ctx = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-5", "claude-fable", "claude-mythos",
                    "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-4-6")
        if any(k in m for k in long_ctx):
            return 1_000_000  # Claude 4.6+ and 5.x: 1M on the Anthropic API and on Bedrock
        # Claude 4.5 and older (Opus/Sonnet/Haiku 4.5): 200k.
        return 200_000

    def bedrock_uses_messages(self, model: str) -> bool:
        """Which Bedrock API serves this model: the Messages API (Claude 5.x, anthropic.* IDs) or Converse."""
        if self.bedrock_api in ("messages", "mantle"):
            return True
        if self.bedrock_api == "converse":
            return False
        return model.startswith("anthropic.")
