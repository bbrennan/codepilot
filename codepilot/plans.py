"""The session plan: the checklist the agent keeps with update_plan, and its lifecycle.

Every update is classified against the plan before it: a new plan, an update, completion, or a clear. A new plan or
a clear retires the previous one (kept in the transcript with its progress), so a plan never silently disappears.
The same Tracker runs live (the tool), on reload (history_events) and after a rewind, so the three always agree.
"""

from __future__ import annotations

import json

STATUSES = ("todo", "doing", "done")
MARK = {"done": "✓", "doing": "→", "todo": "○"}


def normalize(items) -> list[dict]:
    """[{text, status}] from what models send: dicts, bare strings, or the whole list as a JSON string."""
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except ValueError:
            return []
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()[:300]
        if text:
            status = item.get("status", "todo")
            out.append({"text": text, "status": status if status in STATUSES else "todo"})
    return out


def progress(items: list[dict]) -> list[int]:
    return [sum(i["status"] == "done" for i in items), len(items)]


def _complete(items: list[dict] | None) -> bool:
    return bool(items) and all(i["status"] == "done" for i in items)


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def step(prev: list[dict] | None, new: list[dict]) -> dict:
    """What an update means, given the plan before it."""
    retired = {"items": prev, "progress": progress(prev)} if prev and not _complete(prev) else None
    if not new:
        return {"items": [], "kind": "clear", "changes": [], "progress": [0, 0], "retired": retired}
    before = {_key(i["text"]): i["status"] for i in prev or []}
    shared = sum(_key(i["text"]) in before for i in new)
    if prev is None or _complete(prev) or shared * 2 < len(new):  # mostly different steps: a new piece of work
        return {"items": new, "kind": "new", "changes": [], "progress": progress(new), "retired": retired}
    changes = []
    for item in new:
        was = before.get(_key(item["text"]))
        if was is None:
            changes.append(f"+ {item['text']}")
        elif was != item["status"]:
            changes.append(f"{MARK[item['status']]} {item['text']}")
    now = {_key(i["text"]) for i in new}
    changes += [f"− {i['text']}" for i in prev if _key(i["text"]) not in now]
    kind = "complete" if _complete(new) else "update"
    return {"items": new, "kind": kind, "changes": changes, "progress": progress(new), "retired": None}


def summary(event: dict) -> str:
    """The tool's answer to the agent, and the line on its card in the chat."""
    done, total = event["progress"]
    counts = f"({done} of {total} done)"
    changes = " · ".join(event["changes"])
    if event["kind"] == "clear":
        return "Plan cleared."
    if event["kind"] == "new":
        return f"New plan {counts}."
    lead = "Plan complete" if event["kind"] == "complete" else "Plan updated"
    return f"{lead} {counts}: {changes}" if changes else f"Plan unchanged {counts}."


class Tracker:
    """Steps through a session's plan updates in order."""

    def __init__(self):
        self.items: list[dict] | None = None

    def push(self, raw) -> dict:
        event = {"type": "plan", **step(self.items, normalize(raw))}
        self.items = event["items"] or None
        return event


def updates(store, sid: str) -> list[tuple[str, object]]:
    """Every update_plan call in the session, in order (compacted messages included): (tool use id, items)."""
    out = []
    for _, m in store.messages(sid, include_archived=True):
        for b in m["content"]:
            tu = b.get("toolUse")
            if tu and tu.get("name") == "update_plan":
                out.append((tu.get("toolUseId", ""), tu.get("input", {}).get("items")))
    return out


def event_for(store, sid: str, tool_use_id: str, raw) -> dict:
    """The event for one update_plan call, given the calls before it."""
    calls = updates(store, sid)
    ids = [tid for tid, _ in calls]
    before = calls[:ids.index(tool_use_id)] if tool_use_id in ids else calls
    tracker = Tracker()
    for _, items in before:
        tracker.push(items)
    return tracker.push(raw)


def current(store, sid: str) -> dict:
    """The plan as it stands now (after a rewind, say), as a 'restore' event."""
    tracker = Tracker()
    for _, items in updates(store, sid):
        tracker.push(items)
    items = tracker.items or []
    return {"type": "plan", "kind": "restore", "items": items, "changes": [], "progress": progress(items),
            "retired": None}
