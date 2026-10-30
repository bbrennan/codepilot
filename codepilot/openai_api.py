"""OpenAI provider: GPT models via your own OPENAI_API_KEY (or any OpenAI-compatible endpoint).

Uses the official `openai` SDK (install with `uv sync --extra openai`) and the Chat Completions API with
function tools, which OpenAI and most compatible servers (Azure OpenAI, LiteLLM, OpenRouter, vLLM) support.
Set CODEPILOT_OPENAI_BASE_URL for a compatible endpoint.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from typing import Any

from .bedrock import BedrockError
from .config import Config


class OpenAIAPI:
    def __init__(self, cfg: Config, client: Any = None):
        self.cfg = cfg
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise BedrockError("The openai package isn't installed. Run: uv sync --extra openai") from exc
            from .bedrock import prepare_tls

            prepare_tls(self.cfg)  # honours a configured CA bundle, same as every other client
            kwargs: dict[str, Any] = {"max_retries": 4, "timeout": 900}
            if self.cfg.openai_base_url:
                kwargs["base_url"] = self.cfg.openai_base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def stream(self, model: str, system: list[dict], messages: list[dict], tools: list[dict] | None = None,
               max_tokens: int | None = None) -> Iterator[dict]:
        import openai

        if not model:
            raise BedrockError("No OpenAI model configured. Set CODEPILOT_OPENAI_MODEL (run `codepilot doctor` "
                               "to list the models your key can use).")
        req: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": "\n\n".join(b["text"] for b in system)}] + to_openai(messages),
            "max_completion_tokens": max_tokens or self.cfg.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            req["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["inputSchema"]["json"]}}
                for t in tools]
        if self.cfg.effort and self.cfg.effort in ("low", "medium", "high"):
            req["reasoning_effort"] = self.cfg.effort
        text, calls, usage, finish = "", {}, {}, None
        try:
            for chunk in self.client.chat.completions.create(**req):
                if chunk.usage:
                    details = getattr(chunk.usage, "prompt_tokens_details", None)
                    usage = {"inputTokens": chunk.usage.prompt_tokens or 0,
                             "outputTokens": chunk.usage.completion_tokens or 0,
                             "cacheReadInputTokens": getattr(details, "cached_tokens", 0) or 0}
                for choice in chunk.choices or []:
                    delta = choice.delta
                    if delta and delta.content:
                        text += delta.content
                        yield {"type": "text", "text": delta.content}
                    for tc in (delta.tool_calls if delta and delta.tool_calls else []):
                        slot = calls.setdefault(tc.index, {"id": None, "name": "", "args": ""})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function and tc.function.name:
                            slot["name"] += tc.function.name
                            yield {"type": "tool_start", "id": slot["id"] or "", "name": slot["name"]}
                        if tc.function and tc.function.arguments:
                            slot["args"] += tc.function.arguments
                    if choice.finish_reason:
                        finish = choice.finish_reason
        except openai.AuthenticationError as exc:
            raise BedrockError("OpenAI API key missing or invalid. Set OPENAI_API_KEY in .env.") from exc
        except openai.NotFoundError as exc:
            raise BedrockError(f"Model {model!r} not found for this key. Check CODEPILOT_OPENAI_MODEL.") from exc
        except openai.RateLimitError as exc:
            raise BedrockError(f"OpenAI rate limit or quota hit: {exc.message}") from exc
        except openai.BadRequestError as exc:
            raise BedrockError(f"OpenAI rejected the request: {exc.message}") from exc
        except openai.APIStatusError as exc:
            raise BedrockError(f"OpenAI API error {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise BedrockError("Couldn't reach the OpenAI API (network, proxy or TLS).") from exc

        content: list[dict] = [{"text": text}] if text else []
        for _, c in sorted(calls.items()):
            try:
                args = json.loads(c["args"] or "{}")
                tool_use = {"toolUseId": c["id"] or f"call_{len(content)}", "name": c["name"],
                            "input": args if isinstance(args, dict) else {}}
            except json.JSONDecodeError:
                tool_use = {"toolUseId": c["id"] or f"call_{len(content)}", "name": c["name"], "input": {},
                            "_invalid_input": c["args"][:2000]}
            content.append({"toolUse": tool_use})
        stop = "tool_use" if calls else ("max_tokens" if finish == "length" else "end_turn")
        yield {"type": "message", "content": content, "stop_reason": stop, "usage": usage}

    def complete(self, model: str, system: str, prompt: str, max_tokens: int = 4000) -> str:
        out = ""
        for event in self.stream(model, [{"text": system}], [{"role": "user", "content": [{"text": prompt}]}],
                                 None, max_tokens):
            if event["type"] == "message":
                out = "".join(b["text"] for b in event["content"] if "text" in b)
        return out.strip()

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self.client.models.list())


def to_openai(messages: list[dict]) -> list[dict]:
    """Stored (Converse-shaped) messages -> Chat Completions messages."""
    out: list[dict] = []
    for m in messages:
        texts, calls, results, pics = [], [], [], []
        for b in m["content"]:
            if "text" in b:
                texts.append(b["text"])
            elif "image" in b:
                pics.append(_image_part(b))
            elif "toolUse" in b:
                tu = b["toolUse"]
                calls.append({"id": tu["toolUseId"], "type": "function",
                              "function": {"name": tu["name"], "arguments": json.dumps(tu.get("input") or {})}})
            elif "toolResult" in b:
                tr = b["toolResult"]
                body = "\n".join(c.get("text", "") for c in tr.get("content", []))
                results.append({"role": "tool", "tool_call_id": tr["toolUseId"],
                                "content": ("ERROR: " if tr.get("status") == "error" else "") + body})
                pics += [_image_part(c) for c in tr.get("content", []) if "image" in c]  # tool messages are text-only
        if m["role"] == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts) or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:
            out += results
            if pics:
                out.append({"role": "user", "content": [{"type": "text", "text": "\n\n".join(texts) or "(images)"},
                                                        *pics]})
            elif texts:
                out.append({"role": "user", "content": "\n\n".join(texts)})
    return out


def _image_part(b: dict) -> dict:
    img = b["image"]
    data = base64.b64encode(img["source"]["bytes"]).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/{img['format']};base64,{data}"}}
