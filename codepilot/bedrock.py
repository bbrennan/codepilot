"""Thin wrapper over the Bedrock Runtime Converse API (streaming, tool use, prompt caching)."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterator
from typing import Any

from .config import Config

log = logging.getLogger(__name__)

CACHE_POINT = {"cachePoint": {"type": "default"}}


class BedrockError(RuntimeError):
    """A Bedrock failure with a message fit to show the user."""


def explain_error(exc: Exception, cfg: Config) -> str:
    """Turn boto/botocore errors into something actionable."""
    name = type(exc).__name__
    text = str(exc)
    profile = cfg.profile or "<profile>"
    if "SSO" in name or "Token" in name or "ExpiredToken" in text or "sso" in text.lower():
        return f"AWS SSO session missing or expired. Run: aws sso login --profile {profile}"
    if name == "NoCredentialsError":
        return f"No AWS credentials. Set AWS_PROFILE and run: aws sso login --profile {profile}"
    if "SSL" in name or "CERTIFICATE_VERIFY_FAILED" in text:
        return ("TLS verification failed. Keep CODEPILOT_SYSTEM_CERTS=1 (default) or set CODEPILOT_CA_BUNDLE "
                "to the corporate CA bundle.")
    code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
    if code == "AccessDeniedException":
        return f"Bedrock access denied: {text}. Check that the model is enabled for this account/region ({cfg.region})."
    if code == "ValidationException":
        return f"Bedrock rejected the request: {text}"
    if code == "ThrottlingException":
        return f"Bedrock throttled the request after retries: {text}"
    return f"{name}: {text}"


class Bedrock:
    def __init__(self, cfg: Config, client: Any = None):
        self.cfg = cfg
        self._client = client
        self._cache_enabled = cfg.prompt_cache

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = make_client(self.cfg, "bedrock-runtime")
        return self._client

    def _thinking_fields(self) -> dict | None:
        mode = self.cfg.thinking
        if mode in ("", "off", "0", "false", "none"):
            return None
        if mode == "adaptive":
            return {"thinking": {"type": "adaptive"}}
        return {"thinking": {"type": "enabled", "budget_tokens": int(mode)}}

    def _request(self, model: str, system: list[dict], messages: list[dict], tools: list[dict] | None,
                 max_tokens: int | None, cache: bool) -> dict:
        system_blocks = list(system)
        msgs = messages
        tool_specs = [{"toolSpec": t} for t in (tools or [])]
        if cache:
            # Static system text first, then a cache point; dynamic context (notes, summary) follows it.
            system_blocks = []
            for block in system:
                if block.get("dynamic"):
                    continue
                system_blocks.append({"text": block["text"]})
            system_blocks.append(CACHE_POINT)
            system_blocks += [{"text": b["text"]} for b in system if b.get("dynamic")]
            if tool_specs:
                tool_specs.append(CACHE_POINT)
            if msgs:
                # Cache the conversation so far; each tool-loop step re-reads it.
                last = dict(msgs[-1])
                last["content"] = list(last["content"]) + [CACHE_POINT]
                msgs = msgs[:-1] + [last]
        else:
            system_blocks = [{"text": b["text"]} for b in system]
        req: dict[str, Any] = {
            "modelId": model,
            "messages": msgs,
            "system": system_blocks,
            "inferenceConfig": {"maxTokens": max_tokens or self.cfg.max_tokens},
        }
        if tool_specs:
            req["toolConfig"] = {"tools": tool_specs}
        fields = self._thinking_fields()
        if fields:
            req["additionalModelRequestFields"] = fields
        return req

    def stream(self, model: str, system: list[dict], messages: list[dict], tools: list[dict] | None = None,
               max_tokens: int | None = None) -> Iterator[dict]:
        """Yield UI events as the reply streams, then one {"type": "message", ...} with the full reply.

        `system` is a list of {"text": ..., "dynamic": bool}. `tools` are Converse toolSpec dicts.
        """
        try:
            response = self._start(model, system, messages, tools, max_tokens)
            yield from _assemble(response["stream"])
        except BedrockError:
            raise
        except Exception as exc:  # botocore raises many unrelated classes
            raise BedrockError(explain_error(exc, self.cfg)) from exc

    def _start(self, model, system, messages, tools, max_tokens) -> dict:
        if self._cache_enabled:
            try:
                return self.client.converse_stream(**self._request(model, system, messages, tools, max_tokens, True))
            except Exception as exc:
                code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
                if code != "ValidationException" or "cach" not in str(exc).lower():
                    raise
                log.warning("Prompt caching rejected by %s; continuing without it: %s", model, exc)
                self._cache_enabled = False
        return self.client.converse_stream(**self._request(model, system, messages, tools, max_tokens, False))

    def complete(self, model: str, system: str, prompt: str, max_tokens: int = 4000,
                 on_usage: Callable[[dict], None] | None = None) -> str:
        """One-shot text completion (used for summaries and doctor checks)."""
        parts = []
        for event in self.stream(model, [{"text": system}], [{"role": "user", "content": [{"text": prompt}]}],
                                 None, max_tokens):
            if event["type"] == "message":
                parts = [b["text"] for b in event["content"] if "text" in b]
                if on_usage and event.get("usage"):
                    on_usage(event["usage"])
        return "".join(parts).strip()


def _assemble(stream: Any) -> Iterator[dict]:
    blocks: dict[int, dict] = {}
    stop_reason = None
    usage: dict = {}
    for event in stream:
        if "contentBlockStart" in event:
            start = event["contentBlockStart"]
            idx = start.get("contentBlockIndex", 0)
            tool = start.get("start", {}).get("toolUse")
            if tool:
                blocks[idx] = {"kind": "tool", "id": tool["toolUseId"], "name": tool["name"], "input": ""}
                yield {"type": "tool_start", "id": tool["toolUseId"], "name": tool["name"]}
        elif "contentBlockDelta" in event:
            delta_event = event["contentBlockDelta"]
            idx = delta_event.get("contentBlockIndex", 0)
            delta = delta_event["delta"]
            if "text" in delta:
                block = blocks.setdefault(idx, {"kind": "text", "text": ""})
                block["text"] += delta["text"]
                yield {"type": "text", "text": delta["text"]}
            elif "toolUse" in delta:
                blocks[idx]["input"] += delta["toolUse"].get("input", "")
            elif "reasoningContent" in delta:
                rc = delta["reasoningContent"]
                block = blocks.setdefault(idx, {"kind": "reasoning", "text": "", "signature": None, "redacted": None})
                if "text" in rc:
                    block["text"] += rc["text"]
                    yield {"type": "thinking", "text": rc["text"]}
                if "signature" in rc:
                    block["signature"] = rc["signature"]
                if "redactedContent" in rc:
                    block["redacted"] = rc["redactedContent"]
        elif "messageStop" in event:
            stop_reason = event["messageStop"].get("stopReason")
        elif "metadata" in event:
            usage = event["metadata"].get("usage", {}) or {}
        else:
            for key, value in event.items():
                if key.endswith("Exception"):
                    raise BedrockError(f"Bedrock stream error ({key}): {value.get('message', value)}")

    content: list[dict] = []
    for idx in sorted(blocks):
        block = blocks[idx]
        if block["kind"] == "text":
            if block["text"]:
                content.append({"text": block["text"]})
        elif block["kind"] == "tool":
            raw = block["input"] or "{}"
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("tool input is not an object")
                tool_use = {"toolUseId": block["id"], "name": block["name"], "input": parsed}
            except ValueError:
                tool_use = {"toolUseId": block["id"], "name": block["name"], "input": {},
                            "_invalid_input": raw[:2000]}
            content.append({"toolUse": tool_use})
        elif block["kind"] == "reasoning":
            if block["redacted"] is not None:
                content.append({"reasoningContent": {"redactedContent": block["redacted"]}})
            else:
                text = {"text": block["text"]}
                if block["signature"]:
                    text["signature"] = block["signature"]
                content.append({"reasoningContent": {"reasoningText": text}})
    yield {"type": "message", "content": content, "stop_reason": stop_reason, "usage": usage}


def make_client(cfg: Config, service: str) -> Any:
    """Build a boto3 client for the configured profile/region, using OS trust store if asked."""
    import boto3
    from botocore.config import Config as BotoConfig

    prepare_tls(cfg)
    session = boto3.Session(profile_name=cfg.profile, region_name=cfg.region)
    kwargs: dict[str, Any] = {
        "config": BotoConfig(read_timeout=600, connect_timeout=20, retries={"max_attempts": 6, "mode": "adaptive"}),
    }
    if cfg.ca_bundle:
        kwargs["verify"] = cfg.ca_bundle
    if cfg.endpoint_url and service == "bedrock-runtime":
        kwargs["endpoint_url"] = cfg.endpoint_url
    return session.client(service, **kwargs)


def prepare_tls(cfg: Config) -> None:
    """Use the OS trust store (unless a CA bundle was given). Call once at startup, from one thread, before any
    client is built: swapping the SSL implementation while other threads build contexts recurses."""
    if cfg.system_certs and not cfg.ca_bundle:
        _use_system_certs()


_certs_done = False
_certs_lock = threading.Lock()


def _use_system_certs() -> None:
    """Corporate TLS inspection: verify against the macOS keychain instead of certifi's bundle.

    Once only, under a lock: model discovery builds clients from several threads at once, and injecting truststore
    twice makes ssl.SSLContext recurse until "maximum recursion depth exceeded".
    """
    global _certs_done
    with _certs_lock:
        if _certs_done:
            return
        try:
            import truststore

            truststore.inject_into_ssl()
        except ImportError:  # pragma: no cover - truststore is a declared dependency
            log.warning("truststore not installed; using default CA bundle")
        _certs_done = True


class BedrockRouter:
    """Sends each model to the Bedrock API that serves it: Messages API for Claude 5.x (anthropic.* IDs),
    Converse for inference-profile IDs (us./eu./global.anthropic...). Tiers can mix the two."""

    def __init__(self, cfg: Config, converse: Any = None, messages: Any = None):
        self.cfg = cfg
        self._converse = converse
        self._messages = messages

    def pick(self, model: str) -> Any:
        if self.cfg.bedrock_uses_messages(model):
            if self._messages is None:
                from .anthropic_api import AnthropicAPI

                self._messages = AnthropicAPI(self.cfg, bedrock=True)
            return self._messages
        if self._converse is None:
            self._converse = Bedrock(self.cfg)
        return self._converse

    def stream(self, model: str, *args: Any, **kwargs: Any) -> Iterator[dict]:
        return self.pick(model).stream(model, *args, **kwargs)

    def complete(self, model: str, *args: Any, **kwargs: Any) -> str:
        return self.pick(model).complete(model, *args, **kwargs)
