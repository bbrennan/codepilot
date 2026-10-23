"""Anthropic API provider: Claude via your own Anthropic key (ANTHROPIC_API_KEY) instead of Bedrock.

Uses the official `anthropic` SDK (install with `uv sync --extra anthropic`). Messages are stored in the
Bedrock Converse shape everywhere else in codepilot, so this module translates both ways, keeping thinking
blocks (with their signatures) intact so they can be replayed unchanged, as the API requires.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .bedrock import BedrockError
from .config import Config

THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"
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
    def __init__(self, cfg: Config, client: Any = None):
        self.cfg = cfg
        self._client = client

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
            "cache_control": {"type": "ephemeral"},  # cache the conversation so far; each tool step re-reads it
        }
        if tools:
            req["tools"] = [{"name": t["name"], "description": t["description"],
                             "input_schema": t["inputSchema"]["json"], "eager_input_streaming": True} for t in tools]
        betas: list[str] = []
        if _supports_adaptive(model):
            # Keep earlier reasoning valid when codepilot rebuilds history at a boundary (memory compaction,
            # new workspace): mismatched thinking blocks are dropped instead of failing the request.
            req["thinking"] = {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
            betas.append(THINKING_BINDING_BETA)
            if self.cfg.effort:
                req["output_config"] = {"effort": self.cfg.effort}
        elif self.cfg.thinking not in ("", "off", "0", "false", "none", "adaptive"):
            req["thinking"] = {"type": "enabled", "budget_tokens": int(self.cfg.thinking)}
        if _supports_fallbacks(model):
            req["fallbacks"] = "default"
            betas.append(FALLBACK_BETA)
        if betas:
            req["betas"] = betas
        return req

    def stream(self, model: str, system: list[dict], messages: list[dict], tools: list[dict] | None = None,
               max_tokens: int | None = None) -> Iterator[dict]:
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
        except anthropic.AuthenticationError as exc:
            raise BedrockError("Anthropic API key missing or invalid. Set ANTHROPIC_API_KEY in .env.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise BedrockError(f"Anthropic API denied the request: {exc.message}") from exc
        except anthropic.NotFoundError as exc:
            raise BedrockError(f"Model {model!r} not found for this key. Check CODEPILOT_ANTHROPIC_MODEL_*.") from exc
        except anthropic.RateLimitError as exc:
            raise BedrockError(f"Anthropic rate limit hit after retries: {exc.message}") from exc
        except anthropic.BadRequestError as exc:
            raise BedrockError(f"Anthropic API rejected the request: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise BedrockError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise BedrockError("Couldn't reach the Anthropic API (network, proxy or TLS). Behind a corporate proxy, "
                               "keep CODEPILOT_SYSTEM_CERTS=1 or set HTTPS_PROXY.") from exc

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
                blocks.append({"type": "tool_result", "tool_use_id": tr["toolUseId"], "content": text,
                               "is_error": tr.get("status") == "error"})
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

