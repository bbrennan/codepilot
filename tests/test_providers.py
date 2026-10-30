import io
import json
from dataclasses import replace

import pytest
from botocore.exceptions import ClientError

from codepilot import ollama as ollama_mod
from codepilot.bedrock import Bedrock, BedrockError, _assemble
from codepilot.config import Config, load_env_file
from codepilot.ollama import Ollama, to_ollama_messages


def test_assemble_text_tool_and_reasoning():
    stream = [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"reasoningContent": {"text": "hmm"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"reasoningContent": {"signature": "sig"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"text": "Hi "}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"text": "there"}}},
        {"contentBlockStart": {"contentBlockIndex": 2, "start": {"toolUse": {"toolUseId": "x", "name": "read_file"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 2, "delta": {"toolUse": {"input": '{"path": "a'}}}},
        {"contentBlockDelta": {"contentBlockIndex": 2, "delta": {"toolUse": {"input": '.py"}'}}}},
        {"messageStop": {"stopReason": "tool_use"}},
        {"metadata": {"usage": {"inputTokens": 3, "outputTokens": 4}}},
    ]
    events = list(_assemble(stream))
    final = events[-1]
    assert [e["type"] for e in events[:-1]] == ["thinking", "text", "text", "tool_start"]
    assert final["content"] == [
        {"reasoningContent": {"reasoningText": {"text": "hmm", "signature": "sig"}}},
        {"text": "Hi there"},
        {"toolUse": {"toolUseId": "x", "name": "read_file", "input": {"path": "a.py"}}},
    ]
    assert final["stop_reason"] == "tool_use" and final["usage"]["outputTokens"] == 4


def test_assemble_flags_truncated_tool_json():
    stream = [
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {"toolUse": {"toolUseId": "x", "name": "t"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": '{"path": "a'}}}},
        {"messageStop": {"stopReason": "max_tokens"}},
    ]
    tu = list(_assemble(stream))[-1]["content"][0]["toolUse"]
    assert tu["input"] == {} and "_invalid_input" in tu


class FakeBedrockClient:
    def __init__(self, fail_cache=False):
        self.requests = []
        self.fail_cache = fail_cache

    def converse_stream(self, **req):
        self.requests.append(req)
        if self.fail_cache and any("cachePoint" in b for b in req["system"]):
            raise ClientError({"Error": {"Code": "ValidationException", "Message": "caching not supported"}},
                              "ConverseStream")
        return {"stream": [{"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "OK"}}},
                           {"messageStop": {"stopReason": "end_turn"}}]}


def _cfg(**kw):
    return replace(Config.from_env(), **kw)


def test_bedrock_request_shape_with_cache_points():
    client = FakeBedrockClient()
    llm = Bedrock(_cfg(prompt_cache=True, thinking="adaptive"), client=client)
    system = [{"text": "static"}, {"text": "dynamic", "dynamic": True}]
    msgs = [{"role": "user", "content": [{"text": "hi"}]}]
    tools = [{"name": "t", "description": "d", "inputSchema": {"json": {"type": "object"}}}]
    list(llm.stream("m", system, msgs, tools))
    req = client.requests[0]
    assert req["system"] == [{"text": "static"}, {"cachePoint": {"type": "default"}}, {"text": "dynamic"}]
    assert req["toolConfig"]["tools"][-1] == {"cachePoint": {"type": "default"}}
    assert req["messages"][-1]["content"][-1] == {"cachePoint": {"type": "default"}}
    assert msgs[0]["content"] == [{"text": "hi"}]  # caller's history untouched
    assert req["additionalModelRequestFields"] == {"thinking": {"type": "adaptive"}}


def test_bedrock_falls_back_when_caching_rejected():
    client = FakeBedrockClient(fail_cache=True)
    llm = Bedrock(_cfg(prompt_cache=True, thinking="off"), client=client)
    assert llm.complete("m", "sys", "ping") == "OK"
    assert len(client.requests) == 2 and "additionalModelRequestFields" not in client.requests[1]
    assert llm.complete("m", "sys", "ping") == "OK"
    assert len(client.requests) == 3  # stays off afterwards


def test_bedrock_errors_are_explained():
    class Boom:
        def converse_stream(self, **req):
            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "ConverseStream")

    with pytest.raises(BedrockError, match="enabled for this account"):
        msgs = [{"role": "user", "content": [{"text": "x"}]}]
        list(Bedrock(_cfg(), client=Boom()).stream("m", [{"text": "s"}], msgs))


def test_to_ollama_messages():
    msgs = [
        {"role": "user", "content": [{"text": "hi"}]},
        {"role": "assistant", "content": [
            {"text": "let me look"},
            {"toolUse": {"toolUseId": "a", "name": "read_file", "input": {"path": "x"}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "a", "content": [{"text": "body"}],
                                                     "status": "error"}}]},
    ]
    out = to_ollama_messages(msgs)
    assert out[0] == {"role": "user", "content": "hi"}
    assert out[1]["tool_calls"][0]["function"] == {"name": "read_file", "arguments": {"path": "x"}}
    assert out[2] == {"role": "tool", "tool_name": "read_file", "content": "ERROR: body"}


def test_ollama_stream_parsing(monkeypatch):
    lines = [
        {"message": {"role": "assistant", "content": "Hel"}},
        {"message": {"role": "assistant", "content": "lo",
                     "tool_calls": [{"function": {"name": "list_files", "arguments": {"path": "."}}}]}},
        {"done": True, "done_reason": "stop", "prompt_eval_count": 7, "eval_count": 2},
    ]
    body = io.BytesIO(b"".join(json.dumps(x).encode() + b"\n" for x in lines))
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return body

    monkeypatch.setattr(ollama_mod.urllib.request, "urlopen", fake_urlopen)
    tools = [{"name": "list_files", "description": "d", "inputSchema": {"json": {"type": "object"}}}]
    events = list(Ollama(_cfg(provider="ollama")).stream("llama3.2:3b", [{"text": "sys"}],
                                                         [{"role": "user", "content": [{"text": "hi"}]}], tools))
    final = events[-1]
    assert final["stop_reason"] == "tool_use"
    assert final["content"][0] == {"text": "Hello"}
    assert final["content"][1]["toolUse"]["name"] == "list_files"
    assert captured["body"]["tools"][0]["function"]["name"] == "list_files"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_env_file_loading(tmp_path, monkeypatch):
    import os

    monkeypatch.setattr(os, "environ", os.environ.copy())  # keep loaded values from leaking into other tests
    env = tmp_path / ".env"
    env.write_text('# comment\nexport AWS_PROFILE=my-sso-profile\nCODEPILOT_REPO="/path with spaces/repo"\n'
                   "CODEPILOT_TEST_CMD='uv run pytest -q'  \nCODEPILOT_MAX_TOKENS=8000 # inline\n")
    for k in ("AWS_PROFILE", "CODEPILOT_REPO", "CODEPILOT_TEST_CMD", "CODEPILOT_MAX_TOKENS", "CODEPILOT_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CODEPILOT_TEST_CMD", "already set wins")
    load_env_file(env)
    cfg = Config.from_env()
    assert cfg.profile == "my-sso-profile"
    assert cfg.default_repo == "/path with spaces/repo"
    assert cfg.test_cmd == "already set wins"
    assert cfg.max_tokens == 8000


def test_ollama_provider_models(monkeypatch):
    monkeypatch.setenv("CODEPILOT_PROVIDER", "ollama")
    monkeypatch.setenv("CODEPILOT_OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("CODEPILOT_OLLAMA_MODEL_FAST", "llama3.2:3b")
    cfg = Config.from_env()
    assert cfg.models == {"fast": "llama3.2:3b", "main": "qwen2.5-coder:7b", "hard": "qwen2.5-coder:7b"}


def test_ollama_recovers_tool_call_printed_as_text(monkeypatch):
    text = '{"name": "read_file", "parameters": {"path": "a.py"}}'
    lines = [{"message": {"role": "assistant", "content": text}}, {"done": True, "done_reason": "stop"}]
    body = io.BytesIO(b"".join(json.dumps(x).encode() + b"\n" for x in lines))
    monkeypatch.setattr(ollama_mod.urllib.request, "urlopen", lambda req, timeout=None: body)
    tools = [{"name": "read_file", "description": "d", "inputSchema": {"json": {"type": "object"}}}]
    final = list(Ollama(_cfg(provider="ollama")).stream("m", [{"text": "s"}],
                                                        [{"role": "user", "content": [{"text": "hi"}]}], tools))[-1]
    assert final["stop_reason"] == "tool_use"
    assert final["content"] == [{"toolUse": {"toolUseId": final["content"][0]["toolUse"]["toolUseId"],
                                             "name": "read_file", "input": {"path": "a.py"}}}]


def test_system_certs_are_injected_exactly_once_even_when_threads_race(monkeypatch):
    """Model discovery builds clients from 8 threads at once. Injecting truststore twice makes ssl.SSLContext
    recurse ("maximum recursion depth exceeded"), which hid every model as unavailable."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    import truststore

    from codepilot import bedrock

    calls = []

    def slow_inject():
        calls.append(threading.get_ident())
        time.sleep(0.05)

    monkeypatch.setattr(truststore, "inject_into_ssl", slow_inject)
    monkeypatch.setattr(bedrock, "_certs_done", False)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: bedrock._use_system_certs(), range(8)))
    assert len(calls) == 1


def test_a_configured_ca_bundle_means_no_client_injects_the_os_trust_store(cfg, monkeypatch):
    """prepare_tls skips the OS trust store when a CA bundle is set; the Anthropic and OpenAI clients used to inject
    it anyway, from whatever thread built them, which is the race that recursed."""
    from dataclasses import replace

    from codepilot import bedrock
    from codepilot.anthropic_api import AnthropicAPI
    from codepilot.openai_api import OpenAIAPI

    for with_bundle, expected in ((True, 0), (False, 2)):
        injected = []
        monkeypatch.setattr(bedrock, "_use_system_certs", lambda: injected.append(1))
        c = replace(cfg, system_certs=True, ca_bundle="/tmp/bundle.pem" if with_bundle else None, openai_base_url=None)
        for make in (lambda: AnthropicAPI(c).client, lambda: OpenAIAPI(c).client):
            try:
                make()
            except Exception:  # noqa: BLE001 - SDK/client setup may fail without keys; only the TLS step matters
                pass
        assert len(injected) == expected, (with_bundle, injected)
