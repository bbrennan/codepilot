"""Which models can this account actually use?

- Anthropic API, OpenAI, Ollama: their own model-listing endpoints.
- Bedrock: access is granted per account and model, and the Messages API (Claude 5.x) has no listing
  endpoint. So codepilot probes candidates with a minimal request (a few tokens each): the known Claude IDs for
  the Messages API, plus the Converse inference profiles the region lists. Results are cached in
  ~/.codepilot/models.json for 12 hours (refresh from the UI or `codepilot models --refresh`).

Tiers whose configured model isn't available fall back to the best available model in the same family.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .config import TIERS, Config

CACHE_TTL = 12 * 3600

# Claude models served by the Bedrock Messages API (bedrock-mantle), newest first within each family.
BEDROCK_MESSAGES_CATALOG = [
    "anthropic.claude-opus-5-5", "anthropic.claude-opus-5", "anthropic.claude-opus-4-8", "anthropic.claude-opus-4-7",
    "anthropic.claude-sonnet-5-5", "anthropic.claude-sonnet-5",
    "anthropic.claude-haiku-5-5", "anthropic.claude-haiku-4-5",
    "anthropic.claude-fable-5-1", "anthropic.claude-fable-5",
]
# Preferred families per tier, best first, for falling back when a configured model isn't enabled.
TIER_FAMILIES = {"fast": ["haiku", "sonnet"], "main": ["sonnet", "opus"], "hard": ["opus", "fable", "sonnet"]}
DENIED = re.compile(r"access|not authori[sz]ed|not enabled|not available|don't have|do not have|unsupported|"
                    r"not found|invalid model|model identifier|use case|subscribe|agreement|onboard", re.IGNORECASE)


def label(model_id: str) -> str:
    """'us.anthropic.claude-sonnet-4-5-20250929-v1:0' -> 'Claude Sonnet 4.5'."""
    m = re.search(r"claude-(opus|sonnet|haiku|fable|mythos)-(\d+)(?:-(\d+))?(?=$|[-:.])", model_id)
    if not m:
        return model_id
    major = m.group(2)
    minor = m.group(3) if m.group(3) and len(m.group(3)) < 3 else None
    return f"Claude {m.group(1).title()} {major}{'.' + minor if minor else ''}"


def _version(model_id: str) -> tuple:
    m = re.search(r"claude-[a-z]+-(\d+)(?:-(\d+))?", model_id)
    if not m:
        return (0, 0)
    minor = int(m.group(2)) if m.group(2) and len(m.group(2)) < 3 else 0
    return (int(m.group(1)), minor)


def _family(model_id: str) -> str:
    m = re.search(r"claude-([a-z]+)", model_id)
    return m.group(1) if m else ""


def _probe_error(exc: Exception) -> tuple[bool, str]:
    """(available, reason) from a probe failure. Access/model errors mean unavailable; other errors don't."""
    text = str(exc)
    status = getattr(exc, "status_code", None)
    resp = getattr(exc, "response", None)
    code = None
    if isinstance(resp, dict):  # botocore ClientError
        code = resp.get("Error", {}).get("Code")
        status = status or resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
    denied = status in (401, 403, 404) or code in ("AccessDeniedException", "ResourceNotFoundException")
    if denied or DENIED.search(text):
        return False, text.splitlines()[0][:200] if text else type(exc).__name__
    return True, f"reachable (probe returned: {text.splitlines()[0][:120] if text else type(exc).__name__})"


def probe_bedrock(cfg: Config, model: str) -> tuple[bool, str]:
    """Minimal request to see whether this account can call the model."""
    try:
        if cfg.bedrock_uses_messages(model):
            from .anthropic_api import AnthropicAPI

            AnthropicAPI(cfg, bedrock=True).client.messages.create(
                model=model, max_tokens=8, messages=[{"role": "user", "content": "ping"}])
        else:
            from .bedrock import make_client

            make_client(cfg, "bedrock-runtime").converse(
                modelId=model, messages=[{"role": "user", "content": [{"text": "ping"}]}],
                inferenceConfig={"maxTokens": 8})
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - any failure is classified, not raised
        return _probe_error(exc)


def bedrock_candidates(cfg: Config) -> list[str]:
    ids = list(BEDROCK_MESSAGES_CATALOG)
    try:
        from .bedrock import make_client

        resp = make_client(cfg, "bedrock").list_inference_profiles(maxResults=200)
        ids += sorted(p["inferenceProfileId"] for p in resp.get("inferenceProfileSummaries", [])
                      if "anthropic.claude" in p["inferenceProfileId"])
    except Exception:  # noqa: BLE001 - listing is optional; the Messages catalog still gets probed
        pass
    ids += [m for m in cfg.models.values() if m and m not in ids]
    return ids


def discover(cfg: Config, refresh: bool = False, probe: Callable[[Config, str], tuple[bool, str]] | None = None,
             lister: Callable[[Config], list[str]] | None = None) -> dict:
    """Available models for the configured provider (cached)."""
    cache = cfg.home / "models.json"
    key = f"{cfg.provider}|{cfg.region}|{cfg.profile}|{cfg.anthropic_base_url}|{cfg.openai_base_url}|{cfg.ollama_url}"
    if not refresh and cache.exists():
        try:
            data = json.loads(cache.read_text())
            if data.get("key") == key and time.time() - data.get("checked_at", 0) < CACHE_TTL:
                return data
        except (OSError, ValueError):
            pass
    models: list[dict] = []
    if cfg.provider == "bedrock":
        candidates = (lister or bedrock_candidates)(cfg)
        probe = probe or probe_bedrock
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda m: (m, *probe(cfg, m)), candidates))
        for m, ok, reason in results:
            models.append({"id": m, "label": label(m), "available": ok, "reason": reason,
                           "api": "Messages API" if cfg.bedrock_uses_messages(m) else "Converse",
                           "window": cfg.context_window(m)})
    else:
        try:
            ids = (lister or _list_native)(cfg)
            models = [{"id": m, "label": label(m), "available": True, "reason": "listed", "api": cfg.provider,
                       "window": cfg.context_window(m)} for m in ids]
        except Exception as exc:  # noqa: BLE001
            models = [{"id": m, "label": label(m), "available": True, "reason": f"not verified: {exc}"[:200],
                       "api": cfg.provider, "window": cfg.context_window(m)} for m in cfg.models.values() if m]
    models.sort(key=lambda d: (not d["available"], _family(d["id"]), tuple(-v for v in _version(d["id"])), d["id"]))
    data = {"key": key, "provider": cfg.provider, "checked_at": time.time(), "models": models}
    data["tiers"] = resolve_tiers(cfg, data)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, indent=1))
    except OSError:
        pass
    return data


def _list_native(cfg: Config) -> list[str]:
    from .agent import make_llm

    llm = make_llm(cfg)
    return list(llm.list_models())


def cached(cfg: Config) -> dict | None:
    try:
        data = json.loads((cfg.home / "models.json").read_text())
        return data if data.get("provider") == cfg.provider else None
    except (OSError, ValueError):
        return None


def resolve_tiers(cfg: Config, data: dict | None) -> dict[str, dict]:
    """Effective model per tier: the configured one if available, else the best available in its families."""
    out: dict[str, dict] = {}
    known = {m["id"]: m for m in (data or {}).get("models", [])}
    available = [m for m in (data or {}).get("models", []) if m["available"]]
    for tier in TIERS:
        configured = cfg.models[tier]
        info = known.get(configured)
        if info is None or info["available"] or not available:
            out[tier] = {"model": configured, "configured": configured, "fallback": False}
            continue
        pick = None
        for fam in TIER_FAMILIES[tier]:
            same = [m for m in available if _family(m["id"]) == fam]
            if same:
                pick = max(same, key=lambda m: (_version(m["id"]), m["api"] == "Messages API"))["id"]
                break
        out[tier] = {"model": pick or available[0]["id"], "configured": configured, "fallback": True,
                     "reason": info["reason"]}
    return out
