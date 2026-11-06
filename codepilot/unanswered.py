"""Tool calls left without a result.

The assistant's message is stored before its tool calls run, so a crash, a restart or a kill mid-call leaves calls with
no result. Providers reject a conversation like that, so every later message would fail and the session would be stuck.
Before the next message, the calls are closed with a result that says they didn't run, and the conversation goes on.
"""

from __future__ import annotations

NOT_RUN = ("Not run: codepilot stopped before this call finished (a restart or an internal error), so it may not have "
           "happened. Check before relying on it, and run it again if it's still needed.")
NOTE = "(The previous step was interrupted.)"


def calls(store, session_id: str) -> list[dict]:
    """The tool calls in the conversation's last message, if it's the assistant's: nothing answered them."""
    last = store.last_message(session_id)
    if not last or last[1]["role"] != "assistant":
        return []
    return [b["toolUse"] for b in last[1]["content"] if "toolUse" in b]


def close(store, session_id: str) -> list[str]:
    """Answer the unanswered calls, keeping roles alternating so the next message still starts its own turn (it can
    be edited and retried). Returns the names of the tools closed."""
    left = calls(store, session_id)
    if not left:
        return []
    results = [{"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"text": NOT_RUN}], "status": "error"}}
               for tu in left]
    store.add_message(session_id, "user", results)
    store.add_message(session_id, "assistant", [{"text": NOTE}])
    return [tu["name"] for tu in left]
