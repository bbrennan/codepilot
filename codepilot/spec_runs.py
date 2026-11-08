"""Spec runs in the chat: the task card the browser draws for "Run all remaining" (or one task's Run), kept with the
session so that a reload draws it where it was.

The browser drives a run (it sends each task's message and decides, when its turn ends, whether to go on), so it
records the card's state here at each step: before a task's message (that task in progress) and after its turn (how
it ended). Each record remembers the last message so far; a reload replays it after that message, and Edit/Retry,
which remove messages, forget the records made after them.
"""

KEY = "spec_runs"
STATUSES = {"todo", "doing", "done", "paused", "failed"}
ENDINGS = {None, "complete", "paused", "stopped"}
MAX_ITEMS, MAX_TEXT = 200, 500


def _text(value, limit: int = MAX_TEXT, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"expected text of up to {limit} characters")
    return value


def _event(data) -> dict:
    """The card as the browser sent it, checked; ValueError if it isn't one."""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or len(data["items"]) > MAX_ITEMS:
        raise ValueError("a spec run needs run, spec and a list of items")
    items = []
    for it in data["items"]:
        if not isinstance(it, dict) or not isinstance(it.get("status"), str) or it["status"] not in STATUSES:
            raise ValueError(f"each item needs text and a status ({', '.join(sorted(STATUSES))})")
        item = {"text": _text(it.get("text")), "status": it["status"]}
        for key, limit in (("id", 32), ("note", MAX_TEXT)):  # the task's id in tasks.md; how it ended
            if it.get(key):
                item[key] = _text(it[key], limit)
        items.append(item)
    if not isinstance(data.get("ended"), (str, type(None))) or data.get("ended") not in ENDINGS:
        raise ValueError("ended must be complete, paused or stopped")
    event = {"type": "spec_run", "run": _text(data.get("run"), 64), "spec": _text(data.get("spec"), 200),
             "items": items, "ended": data.get("ended")}
    if data.get("why"):  # why a paused run stopped
        event["why"] = _text(data["why"])
    return event


def record(store, sid: str, data) -> dict:
    """Keep the card as it is now, after the last message so far. Returns its event."""
    event = _event(data)
    last = store.last_message(sid)
    state = dict(store.get_session(sid).context_state or {})
    state[KEY] = [*state.get(KEY, []), {**event, "after": last[0] if last else 0}]
    store.update_session(sid, context_state=state)
    return event


def placed(store, sid: str) -> list[tuple[int, dict]]:
    """Each recorded state, with the id of the message it came after, oldest first."""
    return [(r["after"], {k: v for k, v in r.items() if k != "after"})
            for r in (store.get_session(sid).context_state or {}).get(KEY, [])]


def forget_from(store, sid: str, mid: int) -> None:
    """Edit/Retry removed message `mid` and everything after it: so go the states recorded since."""
    state = dict(store.get_session(sid).context_state or {})
    if state.get(KEY):
        state[KEY] = [r for r in state[KEY] if r["after"] < mid]
        store.update_session(sid, context_state=state)
