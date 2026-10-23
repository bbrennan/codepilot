from dataclasses import replace
from types import SimpleNamespace as NS

from codepilot.anthropic_api import AnthropicAPI, from_anthropic, to_anthropic
from codepilot.config import Config
from codepilot.openai_api import OpenAIAPI, to_openai


def _cfg(**kw):
    return replace(Config.from_env(), **kw)


class Block(NS):
    def model_dump(self, exclude_none=True):
        return {k: v for k, v in vars(self).items() if v is not None or not exclude_none}


class FakeAnthropicStream:
    def __init__(self, events, final):
        self.events, self.final = events, final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self.events)

    def get_final_message(self):
        return self.final


class FakeAnthropic:
    def __init__(self, events, final):
        self.requests = []
        outer = self

        class Messages:
            def stream(self, **req):
                outer.requests.append(req)
                return FakeAnthropicStream(events, final)
        self.beta = NS(messages=Messages())


def test_anthropic_request_and_stream():
    final = NS(content=[Block(type="thinking", thinking="", signature="sig-1"),
                        Block(type="text", text="Looking."),
                        Block(type="tool_use", id="tu_1", name="read_file", input={"path": "a.py"})],
               stop_reason="tool_use",
               usage=NS(input_tokens=100, output_tokens=20, cache_read_input_tokens=80, cache_creation_input_tokens=5))
    events = [NS(type="text", text="Looking."),
              NS(type="content_block_start", content_block=NS(type="tool_use", id="tu_1", name="read_file"))]
    fake = FakeAnthropic(events, final)
    llm = AnthropicAPI(_cfg(provider="anthropic", effort="high"), client=fake)
    tools = [{"name": "read_file", "description": "d", "inputSchema": {"json": {"type": "object"}}}]
    history = [{"role": "user", "content": [{"text": "hi"}]}]
    out = list(llm.stream("claude-opus-5-5", [{"text": "sys"}], history, tools))
    req = fake.requests[0]
    assert req["thinking"] == {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
    assert set(req["betas"]) == {"thinking-binding-controls-2026-08-01", "server-side-fallback-2026-07-01"}
    assert req["fallbacks"] == "default" and req["output_config"] == {"effort": "high"}
    assert req["cache_control"] == {"type": "ephemeral"} and req["tools"][0]["eager_input_streaming"] is True
    assert req["system"] == [{"type": "text", "text": "sys"}]
    assert [e["type"] for e in out] == ["text", "tool_start", "message"]
    msg = out[-1]
    assert msg["stop_reason"] == "tool_use"
    assert msg["usage"] == {"inputTokens": 100, "outputTokens": 20, "cacheReadInputTokens": 80,
                            "cacheWriteInputTokens": 5}
    # Thinking signature survives the round trip so the block is replayed unchanged.
    replay = to_anthropic([{"role": "assistant", "content": msg["content"]}])[0]["content"]
    assert replay[0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}
    assert replay[2] == {"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"path": "a.py"}}


def test_anthropic_older_model_and_haiku_have_no_fallbacks():
    final = NS(content=[Block(type="text", text="ok")], stop_reason="end_turn",
               usage=NS(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0))
    fake = FakeAnthropic([], final)
    llm = AnthropicAPI(_cfg(provider="anthropic", effort=""), client=fake)
    list(llm.stream("claude-haiku-5-5", [{"text": "s"}], [{"role": "user", "content": [{"text": "x"}]}]))
    assert "fallbacks" not in fake.requests[0] and "output_config" not in fake.requests[0]
    list(llm.stream("claude-sonnet-4-5", [{"text": "s"}], [{"role": "user", "content": [{"text": "x"}]}]))
    assert "thinking" not in fake.requests[1] and "betas" not in fake.requests[1]


def test_from_anthropic_drops_blocks_before_fallback_and_keeps_unknown():
    blocks = [{"type": "thinking", "thinking": "", "signature": "a"}, {"type": "text", "text": "partial"},
              {"type": "fallback", "model": "x"}, {"type": "thinking", "thinking": "", "signature": "b"},
              {"type": "text", "text": "final"}, {"type": "server_thing", "x": 1}]
    out = from_anthropic(blocks)
    assert out[0] == {"text": "partial"}
    assert out[1]["reasoningContent"]["reasoningText"]["signature"] == "b"
    assert out[-1] == {"anthropicRaw": {"type": "server_thing", "x": 1}}


def test_to_anthropic_tool_results_and_bedrock_redacted():
    msgs = [{"role": "user", "content": [{"toolResult": {"toolUseId": "t", "content": [{"text": "boom"}],
                                                         "status": "error"}}, {"text": "next"}]},
            {"role": "assistant", "content": [{"reasoningContent": {"redactedContent": b"bedrock-bytes"}},
                                              {"text": "hi"}]}]
    out = to_anthropic(msgs)
    assert out[0]["content"][0] == {"type": "tool_result", "tool_use_id": "t", "content": "boom", "is_error": True}
    assert out[1]["content"] == [{"type": "text", "text": "hi"}]


def chunk(content=None, tool_calls=None, finish=None, usage=None):
    delta = NS(content=content, tool_calls=tool_calls)
    return NS(choices=[NS(delta=delta, finish_reason=finish)] if (content or tool_calls or finish) else [],
              usage=usage)


def test_openai_stream_tool_calls():
    chunks = [
        chunk(content="Let me look. "),
        chunk(tool_calls=[NS(index=0, id="call_1", function=NS(name="read_file", arguments='{"pa'))]),
        chunk(tool_calls=[NS(index=0, id=None, function=NS(name=None, arguments='th": "a.py"}'))]),
        chunk(finish="tool_calls"),
        chunk(usage=NS(prompt_tokens=50, completion_tokens=7, prompt_tokens_details=NS(cached_tokens=30))),
    ]
    requests = []
    client = NS(chat=NS(completions=NS(create=lambda **req: requests.append(req) or iter(chunks))))
    llm = OpenAIAPI(_cfg(provider="openai", effort="medium"), client=client)
    tools = [{"name": "read_file", "description": "d", "inputSchema": {"json": {"type": "object"}}}]
    out = list(llm.stream("gpt-x", [{"text": "sys"}], [{"role": "user", "content": [{"text": "hi"}]}], tools))
    msg = out[-1]
    assert msg["content"] == [{"text": "Let me look. "},
                              {"toolUse": {"toolUseId": "call_1", "name": "read_file", "input": {"path": "a.py"}}}]
    assert msg["stop_reason"] == "tool_use"
    assert msg["usage"] == {"inputTokens": 50, "outputTokens": 7, "cacheReadInputTokens": 30}
    req = requests[0]
    assert req["messages"][0] == {"role": "system", "content": "sys"} and req["reasoning_effort"] == "medium"
    assert req["tools"][0]["function"]["name"] == "read_file" and "max_completion_tokens" in req


def test_openai_requires_model():
    import pytest

    from codepilot.bedrock import BedrockError
    with pytest.raises(BedrockError, match="CODEPILOT_OPENAI_MODEL"):
        list(OpenAIAPI(_cfg(provider="openai"), client=NS()).stream("", [{"text": "s"}], []))


def test_to_openai_roundtrip():
    msgs = [{"role": "user", "content": [{"text": "hi"}]},
            {"role": "assistant", "content": [
                {"reasoningContent": {"reasoningText": {"text": "", "signature": "s"}}},
                {"toolUse": {"toolUseId": "c1", "name": "git", "input": {"args": "log"}}}]},
            {"role": "user", "content": [{"toolResult": {"toolUseId": "c1", "content": [{"text": "abc"}],
                                                         "status": "success"}}, {"text": "<turn_context>x"}]}]
    out = to_openai(msgs)
    assert out[1] == {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "git", "arguments": '{"args": "log"}'}}]}
    assert out[2] == {"role": "tool", "tool_call_id": "c1", "content": "abc"}
    assert out[3] == {"role": "user", "content": "<turn_context>x"}


def test_provider_config(monkeypatch):
    for k in ("CODEPILOT_EFFORT", "CODEPILOT_ANTHROPIC_MODEL", "CODEPILOT_OPENAI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CODEPILOT_PROVIDER", "anthropic")
    cfg = Config.from_env()
    assert cfg.models == {"fast": "claude-haiku-5-5", "main": "claude-sonnet-5-5", "hard": "claude-opus-5-5"}
    assert cfg.effort == "high"
    monkeypatch.setenv("CODEPILOT_PROVIDER", "openai")
    monkeypatch.setenv("CODEPILOT_OPENAI_MODEL", "my-model")
    monkeypatch.setenv("CODEPILOT_OPENAI_MODEL_FAST", "my-small")
    cfg = Config.from_env()
    assert cfg.models == {"fast": "my-small", "main": "my-model", "hard": "my-model"} and cfg.effort == ""
