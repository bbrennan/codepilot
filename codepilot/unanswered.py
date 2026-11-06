"""Tool calls left without a result.

The assistant's message is stored before its tool calls run, so a crash, a restart or a kill mid-call leaves calls with
no result, possibly with your next messages stored after them. Providers reject a conversation like that, so every later
message would fail and the session would be stuck.

The stored history isn't rewritten: inserting results mid-conversation would renumber messages (checkpoints and costs
refer to them) or turn your next message into something that can't be edited. Instead, every request gets a result
saying the call didn't run, right after the call; the same text each time, so prompt caching is unaffected. The chat
shows the same result, live (once) and when it's redrawn.
"""

from __future__ import annotations

NOT_RUN = ("Not run: codepilot stopped before this call finished (a restart or an internal error), so it may not have "
           "happened. Check before relying on it, and run it again if it's still needed.")


def _result(tu: dict) -> dict:
    return {"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"text": NOT_RUN}], "status": "error"}}


def _answered_by(message: dict | None) -> set[str]:
    if not message or message["role"] != "user":
        return set()
    return {b["toolResult"]["toolUseId"] for b in message["content"] if "toolResult" in b}


def find(messages: list[dict]) -> list[tuple[int, list[dict]]]:
    """(index of an assistant message, its tool calls that the message after it doesn't answer)."""
    found = []
    for i, m in enumerate(messages):
        if m["role"] != "assistant":
            continue
        answered = _answered_by(messages[i + 1] if i + 1 < len(messages) else None)
        left = [b["toolUse"] for b in m["content"] if "toolUse" in b and b["toolUse"]["toolUseId"] not in answered]
        if left:
            found.append((i, left))
    return found


def repair(messages: list[dict]) -> list[dict]:
    """The conversation as sent to the model: each unanswered call gets its result first in the next user message
    (tool results must lead it), or in a message of its own if nothing follows."""
    gaps = dict(find(messages))
    if not gaps:
        return messages
    out = []
    for i, m in enumerate(messages):
        if i - 1 in gaps:
            results = [_result(tu) for tu in gaps[i - 1]]
            if m["role"] == "user":
                m = {**m, "content": results + m["content"]}
            else:
                out.append({"role": "user", "content": results})
        out.append(m)
    if len(messages) - 1 in gaps:
        out.append({"role": "user", "content": [_result(tu) for tu in gaps[len(messages) - 1]]})
    return out


def result_event(tu: dict) -> dict:
    return {"type": "tool_result", "id": tu["toolUseId"], "name": tu["name"], "output": NOT_RUN, "is_error": True,
            "seconds": 0.0}


def announce(store, session_id: str) -> list[dict]:
    """Events for calls nobody has been told about yet: a result for each card in the chat, and one notice."""
    sess = store.get_session(session_id)
    state = dict(sess.context_state or {})
    told = set(state.get("unanswered_told", []))
    new = [tu for _, calls in find(store.live_messages(session_id)) for tu in calls if tu["toolUseId"] not in told]
    if not new:
        return []
    state["unanswered_told"] = sorted(told | {tu["toolUseId"] for tu in new})
    store.update_session(session_id, context_state=state)
    names = ", ".join(dict.fromkeys(tu["name"] for tu in new))
    return [*(result_event(tu) for tu in new),
            {"type": "notice", "message": f"An earlier step ({names}) was interrupted before it finished, so codepilot "
                                          "was told it may not have run."}]
