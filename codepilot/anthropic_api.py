"""Anthropic API provider: Claude via your own Anthropic key (ANTHROPIC_API_KEY) instead of Bedrock.

Uses the official `anthropic` SDK (install with `uv sync --extra anthropic`). Messages are stored in the
Bedrock Converse shape everywhere else in codepilot, so this module translates both ways, keeping thinking
blocks (with their signatures) intact so they can be replayed unchanged, as the API requires.
"""

from __future__ import annotations

import base64

from collections.abc import Iterator
from typing import Any

from .bedrock import BedrockError
from .config import Config

THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"
# Optional request features an endpoint might not support yet; dropped and retried if a 400 names them.
COMPAT_KEYS = {"betas": ("beta", "block_binding", "thinking-binding"), "eager": ("eager_input_streaming",),
               "cache": ("cache_control",), "effort": ("effort", "output_config")}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _supports_adaptive(model: str) -> bool:
    """Claude 4.6+ / 5.x take adaptive thinking; older 4.x models do not."""
    old = ("claude-3", "claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-5", "claude-opus-4-1",
           "claude-opus-4-0", "claude-sonnet-4-0", "claude-opus-4-2", "claude-sonnet-4-2")
    return not model.startswith(old)


def _supports_fallbacks(model: str) -> bool:
    """Server-side refusal fallbacks ('default' form) on the Claude API."""
    return model.startswith(("claude-opus-5", "claude-sonnet-5-5", "claude-fable"))


class AnthropicAPI:
    """Claude via the Messages API: the Anthropic API, or Claude in Amazon Bedrock (`bedrock=True`, the
    bedrock-mantle endpoint, signed with your AWS credentials) where the Claude 5.x models live."""

    def __init__(self, cfg: Config, client: Any = None, bedrock: bool = False):
        self.cfg = cfg
        self._client = client
        self.bedrock = bedrock
        self._disabled: set[str] = set()
        self.label = "Bedrock (Messages API)" if bedrock else "Anthropic API"

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise BedrockError("The anthropic package isn't installed. Run: uv sync --extra anthropic") from exc
            if self.cfg.system_certs:
                from .bedrock import _use_system_certs

                _use_system_certs()
            kwargs: dict[str, Any] = {"max_retries": 4, "timeout": 900}
            if self.bedrock:
                kwargs.update(aws_region=self.cfg.region, aws_profile=self.cfg.profile)
                if self.cfg.bedrock_messages_url:
                    kwargs["base_url"] = self.cfg.bedrock_messages_url
                self._client = anthropic.AnthropicBedrockMantle(**kwargs)
            else:
                if self.cfg.anthropic_base_url:
                    kwargs["base_url"] = self.cfg.anthropic_base_url
                self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def _request(self, model: str, system: list[dict], messages: list[dict], tools: list[dict] | None,
                 max_tokens: int | None) -> dict:
        req: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "system": [{"type": "text", "text": b["text"]} for b in system],
            "messages": to_anthropic(messages),
        }
        if "cache" not in self._disabled:
            if self.bedrock:
                _add_cache_breakpoints(req)  # explicit breakpoints: the portable form of prompt caching
            else:
                req["cache_control"] = {"type": "ephemeral"}  # caches the conversation so far
        if tools:
            req["tools"] = [{"name": t["name"], "description": t["description"],
                             "input_schema": t["inputSchema"]["json"]} for t in tools]
            if "eager" not in self._disabled:
                for t in req["tools"]:
                    t["eager_input_streaming"] = True
        betas: list[str] = []
        if _supports_adaptive(model):
            req["thinking"] = {"type": "adaptive"}
            if "betas" not in self._disabled:
                # Keep earlier reasoning valid when codepilot rebuilds history at a boundary (memory compaction,
                # new workspace): mismatched thinking blocks are dropped instead of failing the request.
                req["thinking"]["block_binding"] = {"prefix_mismatch_behavior": "drop_block"}
                betas.append(THINKING_BINDING_BETA)
            if self.cfg.effort and "effort" not in self._disabled:
                req["output_config"] = {"effort": self.cfg.effort}
        elif self.cfg.thinking not in ("", "off", "0", "false", "none", "adaptive"):
            req["thinking"] = {"type": "enabled", "budget_tokens": int(self.cfg.thinking)}
        if _supports_fallbacks(model) and not self.bedrock and "betas" not in self._disabled:
            req["fallbacks"] = "default"  # not offered on Bedrock
            betas.append(FALLBACK_BETA)
        if betas:
            req["betas"] = betas
        return req

    def stream(self, model: str, system: list[dict], messages: list[dict], tools: list[dict] | None = None,
               max_tokens: int | None = None) -> Iterator[dict]:
        import anthropic

        for _attempt in range(len(COMPAT_KEYS) + 1):
            try:
                yield from self._stream_once(model, system, messages, tools, max_tokens)
                return
            except anthropic.BadRequestError as exc:
                msg = str(exc.message).lower()
                hit = [k for k, words in COMPAT_KEYS.items()
                       if k not in self._disabled and any(w in msg for w in words)]
                if not hit:
                    raise BedrockError(f"{self.label} rejected the request: {exc.message}") from exc
                self._disabled.update(hit)  # this endpoint doesn't take that option: retry without it

    def _stream_once(self, model, system, messages, tools, max_tokens) -> Iterator[dict]:
        import anthropic

        try:
            with self.client.beta.messages.stream(**self._request(model, system, messages, tools, max_tokens)) as s:
                for event in s:
                    etype = getattr(event, "type", "")
                    if etype == "text":
                        yield {"type": "text", "text": event.text}
                    elif etype == "thinking" and getattr(event, "thinking", ""):
                        yield {"type": "thinking", "text": event.thinking}
                    elif etype == "content_block_start" and getattr(event.content_block, "type", "") == "tool_use":
                        yield {"type": "tool_start", "id": event.content_block.id, "name": event.content_block.name}
                final = s.get_final_message()
        except ValueError as exc:  # tool input JSON the SDK couldn't parse at all
            raise BedrockError(f"The model produced unparseable tool input; please retry. ({exc})") from exc
        except anthropic.BadRequestError:
            raise  # handled by stream(): may retry without an unsupported option
        except anthropic.AuthenticationError as exc:
            hint = (f"AWS credentials rejected. Run: aws sso login --profile {self.cfg.profile or '<profile>'}"
                    if self.bedrock else "Anthropic API key missing or invalid. Set ANTHROPIC_API_KEY in .env.")
            raise BedrockError(hint) from exc
        except anthropic.PermissionDeniedError as exc:
            hint = (" Your IAM role needs bedrock-mantle:CreateInference on this model." if self.bedrock else "")
            raise BedrockError(f"{self.label} denied the request: {exc.message}.{hint}") from exc
        except anthropic.NotFoundError as exc:
            where = "CODEPILOT_MODEL_* (Bedrock IDs look like anthropic.claude-opus-5-5)" if self.bedrock \
                else "CODEPILOT_ANTHROPIC_MODEL_*"
            raise BedrockError(f"Model {model!r} not found. Check {where}.") from exc
        except anthropic.RateLimitError as exc:
            raise BedrockError(f"{self.label} rate limit hit after retries: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise BedrockError(f"{self.label} error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise BedrockError(f"Couldn't reach the {self.label} (network, proxy or TLS). Behind a corporate proxy, "
                               "keep CODEPILOT_SYSTEM_CERTS=1 or set HTTPS_PROXY.") from exc
        except Exception as exc:  # e.g. AWS credential/SSO errors raised while signing the request
            if not self.bedrock:
                raise
            from .bedrock import explain_error

            raise BedrockError(explain_error(exc, self.cfg)) from exc

        content = from_anthropic([b.model_dump(exclude_none=True) for b in final.content])
        stop = final.stop_reason
        if stop == "refusal":
            content.append({"text": "(The model declined this request.)"})
            stop = "end_turn"
        u = final.usage
        usage = {"inputTokens": u.input_tokens or 0, "outputTokens": u.output_tokens or 0,
                 "cacheReadInputTokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cacheWriteInputTokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
        yield {"type": "message", "content": content, "stop_reason": stop, "usage": usage}

    def complete(self, model: str, system: str, prompt: str, max_tokens: int = 4000) -> str:
        out = ""
        for event in self.stream(model, [{"text": system}], [{"role": "user", "content": [{"text": prompt}]}],
                                 None, max_tokens):
            if event["type"] == "message":
                out = "".join(b["text"] for b in event["content"] if "text" in b)
        return out.strip()

    def list_models(self) -> list[str]:
        return [m.id for m in self.client.models.list(limit=100)]


def _add_cache_breakpoints(req: dict) -> None:
    """Cache breakpoints on the system prompt and on the latest message (at most 4 are allowed)."""
    if req["system"]:
        req["system"][-1]["cache_control"] = {"type": "ephemeral"}
    if req["messages"]:
        for block in reversed(req["messages"][-1]["content"]):
            if block.get("type") in ("text", "tool_result", "tool_use"):
                block["cache_control"] = {"type": "ephemeral"}
                break


def from_anthropic(blocks: list[dict]) -> list[dict]:
    """Anthropic content blocks -> codepilot's stored (Converse-shaped) blocks."""
    # After a mid-output server-side fallback, reasoning/tool blocks before the last `fallback` marker must
    # not be echoed back; text before it is kept.
    last_fb = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=-1)
    out: list[dict] = []
    for i, b in enumerate(blocks):
        t = b.get("type")
        if i < last_fb and t in ("thinking", "redacted_thinking", "tool_use"):
            continue
        if t == "text":
            if b.get("text"):
                out.append({"text": b["text"]})
        elif t == "tool_use":
            out.append({"toolUse": {"toolUseId": b["id"], "name": b["name"], "input": b.get("input") or {}}})
        elif t == "thinking":
            out.append({"reasoningContent": {"reasoningText": {"text": b.get("thinking", ""),
                                                               "signature": b.get("signature", "")}}})
        elif t == "redacted_thinking":
            out.append({"reasoningContent": {"redactedContent": b.get("data", "")}})
        elif t == "fallback":
            continue
        else:
            out.append({"anthropicRaw": b})  # unknown block types are replayed exactly as received
    return out


def _image(b: dict) -> dict:
    img = b["image"]
    return {"type": "image", "source": {"type": "base64", "media_type": f"image/{img['format']}",
                                        "data": base64.b64encode(img["source"]["bytes"]).decode()}}


def to_anthropic(messages: list[dict]) -> list[dict]:
    """Stored (Converse-shaped) messages -> Anthropic Messages API messages."""
    out = []
    for m in messages:
        blocks: list[dict] = []
        for b in m["content"]:
            if "text" in b:
                if b["text"]:
                    blocks.append({"type": "text", "text": b["text"]})
            elif "toolUse" in b:
                tu = b["toolUse"]
                blocks.append({"type": "tool_use", "id": tu["toolUseId"], "name": tu["name"],
                               "input": tu.get("input") or {}})
            elif "toolResult" in b:
                tr = b["toolResult"]
                text = "\n".join(c.get("text", "") for c in tr.get("content", [])) or "(empty)"
                pics = [_image(c) for c in tr.get("content", []) if "image" in c]
                blocks.append({"type": "tool_result", "tool_use_id": tr["toolUseId"],
                               "content": [{"type": "text", "text": text}, *pics] if pics else text,
                               "is_error": tr.get("status") == "error"})
            elif "image" in b:
                blocks.append(_image(b))
            elif "reasoningContent" in b:
                rc = b["reasoningContent"]
                if "reasoningText" in rc and rc["reasoningText"].get("signature"):
                    blocks.append({"type": "thinking", "thinking": rc["reasoningText"].get("text", ""),
                                   "signature": rc["reasoningText"]["signature"]})
                elif "redactedContent" in rc:
                    data = rc["redactedContent"]
                    if isinstance(data, bytes):  # came from Bedrock; not readable by the Anthropic API
                        continue
                    blocks.append({"type": "redacted_thinking", "data": data})
            elif "anthropicRaw" in b:
                blocks.append(b["anthropicRaw"])
            elif "cachePoint" in b:
                continue
        if not blocks:
            blocks = [{"type": "text", "text": "(empty)"}]
        out.append({"role": m["role"], "content": blocks})
    return out

