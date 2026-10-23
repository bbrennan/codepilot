"""Ollama provider: a free local model for exercising codepilot without AWS.

Speaks Ollama's native /api/chat (streaming NDJSON, tool calling) and translates to and from
the Bedrock Converse message shape the rest of the app uses, so the agent loop is identical.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from typing import Any

from .bedrock import BedrockError
from .config import Config


class Ollama:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def stream(self, model: str, system: list[dict], messages: list[dict], tools: list[dict] | None = None,
               max_tokens: int | None = None) -> Iterator[dict]:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": "\n\n".join(b["text"] for b in system)}]
            + to_ollama_messages(messages),
            "stream": True,
            "options": {"num_predict": min(max_tokens or self.cfg.max_tokens, 8192),
                        "num_ctx": self.cfg.ollama_num_ctx},
        }
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["inputSchema"]["json"]}}
                for t in tools]
        req = urllib.request.Request(f"{self.cfg.ollama_url}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=900)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            if exc.code == 404 and "model" in detail:
                raise BedrockError(f"Ollama model {model!r} not found. Run: ollama pull {model}") from exc
            raise BedrockError(f"Ollama error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BedrockError(f"Cannot reach Ollama at {self.cfg.ollama_url} ({exc.reason}). "
                               "Run: ollama serve") from exc

        text, thinking, calls, usage, done_reason = "", "", [], {}, None
        with resp:
            for raw in resp:
                if not raw.strip():
                    continue
                chunk = json.loads(raw)
                if chunk.get("error"):
                    raise BedrockError(f"Ollama: {chunk['error']}")
                msg = chunk.get("message") or {}
                if msg.get("thinking"):
                    thinking += msg["thinking"]
                    yield {"type": "thinking", "text": msg["thinking"]}
                if msg.get("content"):
                    text += msg["content"]
                    yield {"type": "text", "text": msg["content"]}
                for call in msg.get("tool_calls") or []:
                    fn = call.get("function", {})
                    tid = f"ollama-{uuid.uuid4().hex[:10]}"
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    calls.append({"toolUseId": tid, "name": fn.get("name", ""), "input": args})
                    yield {"type": "tool_start", "id": tid, "name": fn.get("name", "")}
                if chunk.get("done"):
                    done_reason = chunk.get("done_reason")
                    usage = {"inputTokens": chunk.get("prompt_eval_count", 0),
                             "outputTokens": chunk.get("eval_count", 0)}
        if not calls and tools:
            recovered = _text_tool_call(text, {t["name"] for t in tools})
            if recovered:
                calls.append(recovered)
                yield {"type": "tool_start", "id": recovered["toolUseId"], "name": recovered["name"]}
                text = ""
        content: list[dict] = []
        if text:
            content.append({"text": text})
        content += [{"toolUse": c} for c in calls]
        stop = "tool_use" if calls else ("max_tokens" if done_reason == "length" else "end_turn")
        yield {"type": "message", "content": content, "stop_reason": stop, "usage": usage}

    def complete(self, model: str, system: str, prompt: str, max_tokens: int = 4000) -> str:
        out = ""
        for event in self.stream(model, [{"text": system}], [{"role": "user", "content": [{"text": prompt}]}],
                                 None, max_tokens):
            if event["type"] == "message":
                out = "".join(b["text"] for b in event["content"] if "text" in b)
        return out.strip()

    def list_models(self) -> list[str]:
        with urllib.request.urlopen(f"{self.cfg.ollama_url}/api/tags", timeout=10) as resp:
            return [m["name"] for m in json.load(resp).get("models", [])]


def _text_tool_call(text: str, names: set[str]) -> dict | None:
    """Small local models sometimes print a tool call as JSON instead of using the tool API."""
    raw = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if not (raw.startswith("{") and raw.endswith("}")):
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    name = obj.get("name") if isinstance(obj, dict) else None
    args = obj.get("parameters", obj.get("arguments", {})) if isinstance(obj, dict) else None
    if name not in names or not isinstance(args, dict):
        return None
    return {"toolUseId": f"ollama-{uuid.uuid4().hex[:10]}", "name": name, "input": args}


def to_ollama_messages(messages: list[dict]) -> list[dict]:
    """Converse-shaped messages -> Ollama chat messages."""
    out: list[dict] = []
    names: dict[str, str] = {}
    for m in messages:
        texts, calls, results = [], [], []
        for block in m["content"]:
            if "text" in block:
                texts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                names[tu["toolUseId"]] = tu["name"]
                calls.append({"function": {"name": tu["name"], "arguments": tu.get("input", {})}})
            elif "toolResult" in block:
                tr = block["toolResult"]
                body = "\n".join(c.get("text", "") for c in tr.get("content", []))
                if tr.get("status") == "error":
                    body = "ERROR: " + body
                results.append({"role": "tool", "tool_name": names.get(tr["toolUseId"], ""), "content": body})
        if m["role"] == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts)}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:
            out += results
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
    return out
