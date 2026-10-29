"""Which models can this account actually use?

- Anthropic API, OpenAI, Ollama: their own model-listing endpoints.
- Bedrock: access is granted per account and model, and the Messages API (Claude 5.x) has no listing
  endpoint. So codepilot probes candidates with a minimal request (a few tokens each): the known Claude IDs for
  the Messages API, plus the Converse inference profiles the region lists (or, when the role may not list them,
  the known Claude 4.x profile IDs). Only a model that answers counts as available. Results are cached in
  ~/.codepilot/models.json for 12 hours (refresh from the UI or `codepilot models --refresh`).

Each tier uses the newest available model in its configured model's family (Sonnet 4.6 when .env says Sonnet
4.5), unless CODEPILOT_LATEST_MODELS=0; a tier whose family isn't available falls back to the next family.
"""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .config import TIERS, Config

CACHE_TTL = 12 * 3600
_discover_lock = threading.Lock()  # one probe run at a time; concurrent callers then read its cache

# Claude models served by the Bedrock Messages API (bedrock-mantle), newest first within each family.
BEDROCK_MESSAGES_CATALOG = [
    "anthropic.claude-opus-5-5", "anthropic.claude-opus-5", "anthropic.claude-opus-4-8", "anthropic.claude-opus-4-7",
    "anthropic.claude-sonnet-5-5", "anthropic.claude-sonnet-5",
    "anthropic.claude-haiku-5-5", "anthropic.claude-haiku-4-5",
    "anthropic.claude-fable-5-1", "anthropic.claude-fable-5",
]
# Claude 4.x base model IDs for Converse, newest first. Used to build inference-profile IDs when the role can't
# list them (bedrock:ListInferenceProfiles / ListFoundationModels are often denied on locked-down accounts).
BEDROCK_CONVERSE_CATALOG = [
    "anthropic.claude-opus-4-6-v1", "anthropic.claude-opus-4-5-20251101-v1:0",
    "anthropic.claude-sonnet-4-6", "anthropic.claude-sonnet-4-5-20250929-v1:0",
    "anthropic.claude-haiku-4-5-20251001-v1:0",
]
# Preferred families per tier, best first, for falling back when a configured model isn't enabled.
TIER_FAMILIES = {"fast": ["haiku", "sonnet"], "main": ["sonnet", "opus"], "hard": ["opus", "fable", "sonnet"]}
DENIED = re.compile(r"access|not authori[sz]ed|not enabled|not available|don't have|do not have|unsupported (?:region|model)|"
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


CREDENTIALS = re.compile(r"token|credential|signature|security|expired|sso", re.I)
BUSY = re.compile(r"throttl|too many requests|rate exceeded|overloaded|service unavailable|try again", re.I)


def _probe_error(exc: Exception) -> tuple[bool, str]:
    """(available, reason) from a probe failure.

    Available only when the model itself answered: busy (429/5xx, throttling), or it rejected the tiny request's
    parameters (a 400 that isn't about access). Access, model-ID, credential and connection errors mean
    unavailable, so models this account can't call never show up as usable.
    """
    text = str(exc)
    first = text.splitlines()[0][:200] if text else type(exc).__name__
    status = getattr(exc, "status_code", None)
    resp = getattr(exc, "response", None)
    code = None
    if isinstance(resp, dict):  # botocore ClientError
        code = resp.get("Error", {}).get("Code")
        status = status or resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
    if status in (401, 403, 404) or code in ("AccessDeniedException", "ResourceNotFoundException") or DENIED.search(text):
        return False, first
    if status == 429 or (status or 0) >= 500 or code in ("ThrottlingException", "ServiceUnavailableException",
                                                          "ModelNotReadyException") or BUSY.search(text):
        return True, f"available (busy when checked: {first[:120]})"
    if code == "ValidationException" or (status == 400 and code is None and not CREDENTIALS.search(text)):
        return True, f"available (the probe was rejected: {first[:120]})"
    return False, first


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


def _geo(region: str) -> str:
    return {"us": "us", "eu": "eu", "ap": "apac", "ca": "us", "sa": "us"}.get(region.split("-")[0], "")


def bedrock_candidates(cfg: Config) -> list[str]:
    from .bedrock import make_client

    ids = list(BEDROCK_MESSAGES_CATALOG)
    listed: list[str] = []
    try:
        client = make_client(cfg, "bedrock")
        token = None
        while True:
            resp = client.list_inference_profiles(maxResults=1000, **({"nextToken": token} if token else {}))
            listed += [p["inferenceProfileId"] for p in resp.get("inferenceProfileSummaries", [])]
            token = resp.get("nextToken")
            if not token:
                break
    except Exception:  # noqa: BLE001 - listing is often denied; fall back to the known profile IDs below
        listed = [f"{prefix}.{base}" for base in BEDROCK_CONVERSE_CATALOG for prefix in (_geo(cfg.region), "global")
                  if prefix]
    ids += sorted(p for p in listed if _worth_probing(p, cfg.region))
    ids += [m for m in cfg.models.values() if m and m not in ids]
    return list(dict.fromkeys(ids))


def _worth_probing(profile_id: str, region: str) -> bool:
    """Claude 4.5+ inference profiles for this region's geography (or global); skips other geos and models
    Anthropic has retired or is retiring (Claude 4.0 and 4.1)."""
    prefix = profile_id.split(".", 1)[0]
    return "anthropic.claude" in profile_id and prefix in (_geo(region), "global") and _version(profile_id) >= (4, 5)


def discover(cfg: Config, refresh: bool = False, probe: Callable[[Config, str], tuple[bool, str]] | None = None,
             lister: Callable[[Config], list[str]] | None = None) -> dict:
    """Available models for the configured provider (cached)."""
    with _discover_lock:
        return _discover(cfg, refresh, probe, lister)


def _discover(cfg: Config, refresh: bool, probe: Callable[[Config, str], tuple[bool, str]] | None,
              lister: Callable[[Config], list[str]] | None) -> dict:
    cache = cfg.home / "models.json"
    key = (f"v2|{cfg.provider}|{cfg.region}|{cfg.profile}|{cfg.anthropic_base_url}|{cfg.openai_base_url}|"
           f"{cfg.ollama_url}")
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
    _annotate(models, cfg)
    models.sort(key=lambda d: (not d["available"], _family_rank(d["id"]), tuple(-v for v in _version(d["id"])),
                               "same_as" in d, d["id"]))
    data = {"key": key, "provider": cfg.provider, "checked_at": time.time(), "models": models}
    data["tiers"] = resolve_tiers(cfg, data)
    if any(m["available"] for m in models):  # an all-failed run (expired login, no network) is retried next time
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, indent=1))
        except OSError:
            pass
    return data


FAMILY_ORDER = ("fable", "mythos", "opus", "sonnet", "haiku")


def _family_rank(model_id: str) -> int:
    fam = _family(model_id)
    return FAMILY_ORDER.index(fam) if fam in FAMILY_ORDER else len(FAMILY_ORDER)


def _prefix(model_id: str) -> str:
    """'us' for 'us.anthropic.claude-…', '' for a base model ID."""
    head = model_id.split(".", 1)[0]
    return head if "." in model_id and head != "anthropic" else ""


def _annotate(models: list[dict], cfg: Config) -> None:
    """Mark the model to show for each Claude version (others get same_as), and the newest of each family.

    The same version is often reachable several ways (Messages API, us. and global. profiles). The one shown
    is the configured one, else the Messages API, else this region's geography, else global.
    """
    configured = set(cfg.models.values())
    geo = _geo(cfg.region) if cfg.provider == "bedrock" else ""
    groups: dict[tuple, list[dict]] = {}
    for m in models:
        if m["available"] and _family(m["id"]):
            groups.setdefault((_family(m["id"]), _version(m["id"])), []).append(m)
    newest: dict[str, tuple] = {}
    for (fam, ver), same in groups.items():
        same.sort(key=lambda m: (m["id"] not in configured, m["api"] != "Messages API", _prefix(m["id"]) != geo,
                                 _prefix(m["id"]) != "global", len(m["id"])))
        for other in same[1:]:
            other["same_as"] = same[0]["id"]
        newest[fam] = max(newest.get(fam, ver), ver)
    for (fam, ver), same in groups.items():
        if ver == newest[fam]:
            same[0]["newest"] = True


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


AUTO_FAMILIES = {"fast": "haiku", "main": "sonnet", "hard": "opus"}


def best_in_family(data: dict | None, family: str, like: str = "") -> str | None:
    """The newest available model of a family, from discovery results. On a tie: the Messages API, then the
    same kind of ID as `like` (a us. profile when the configured model is one), then the one shown in the list."""
    same = [m for m in (data or {}).get("models", []) if m["available"] and _family(m["id"]) == family]
    if not same:
        return None
    return max(same, key=lambda m: (_version(m["id"]), m["api"] == "Messages API",
                                    bool(like) and _prefix(m["id"]) == _prefix(like), "same_as" not in m))["id"]


def resolve_tiers(cfg: Config, data: dict | None) -> dict[str, dict]:
    """Effective model per tier.

    With CODEPILOT_LATEST_MODELS (the default), the newest available model in the configured model's family:
    a newer Sonnet replaces an older configured one ("upgraded"). If the configured model isn't available and
    its family has nothing newer, the tier falls back to the best available in its families ("fallback").
    Without discovery results, the configured model.
    """
    out: dict[str, dict] = {}
    known = {m["id"]: m for m in (data or {}).get("models", [])}
    available = [m for m in (data or {}).get("models", []) if m["available"]]
    for tier in TIERS:
        configured = cfg.models[tier]
        info = known.get(configured)
        fam = _family(configured)
        if available and fam and cfg.latest_models:
            best = best_in_family(data, fam, like=configured)
            if best and best != configured and _version(best) > _version(configured):
                out[tier] = {"model": best, "configured": configured, "fallback": False, "upgraded": True}
                continue
            if best and info is not None and not info["available"]:  # e.g. global. when us. isn't enabled
                out[tier] = {"model": best, "configured": configured, "fallback": True, "reason": info["reason"]}
                continue
        if info is None or info["available"] or not available:
            out[tier] = {"model": configured, "configured": configured, "fallback": False}
            continue
        pick = None
        for f in TIER_FAMILIES[tier]:
            pick = best_in_family(data, f, like=configured)
            if pick:
                break
        out[tier] = {"model": pick or available[0]["id"], "configured": configured, "fallback": True,
                     "reason": info["reason"]}
    return out
