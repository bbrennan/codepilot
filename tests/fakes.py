"""Test doubles shared by the unit tests (import from here, not from conftest)."""

import copy


class FakeLLM:
    """Replays scripted assistant turns. Each script item is a list of Converse content blocks."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def stream(self, model, system, messages, tools=None, max_tokens=None):
        self.calls.append({"model": model, "system": system, "messages": copy.deepcopy(messages),
                           "tools": tools})
        content = self.script.pop(0)
        for block in content:
            if "text" in block:
                yield {"type": "text", "text": block["text"]}
        stop = "tool_use" if any("toolUse" in b for b in content) else "end_turn"
        yield {"type": "message", "content": content, "stop_reason": stop,
               "usage": {"inputTokens": 10, "outputTokens": 5}}

    def complete(self, model, system, prompt, max_tokens=4000):
        self.calls.append({"complete": prompt})
        return "SUMMARY: earlier work"


def tool_use(tid, name, **inp):
    return {"toolUse": {"toolUseId": tid, "name": name, "input": inp}}
