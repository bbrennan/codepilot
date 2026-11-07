"""The session plan: the checklist the agent keeps with update_plan, and its lifecycle.

Every update is classified against the plan before it: a new plan, an update, completion, or a clear. A new plan or
a clear retires the previous one (kept in the transcript with its progress), so a plan never silently disappears.
The same Tracker runs live (the tool), on reload (history_events) and after a rewind, so the three always agree.

You can dismiss a plan a turn left unfinished. That's a clear made by you instead of the model, tied to the update it
followed (by tool use id, so editing an earlier message can't make it apply to another plan). The model is told once.
"""

from __future__ import annotations

import json

STATUSES = ("todo", "doing", "done")
MARK = {"done": "✓", "doing": "→", "todo": "○"}


def normalize(items) -> list[dict]:
    """[{text, status}] from what models send: dicts, bare strings, or the whole list as a JSON string or as lines
    (as the tool's own argument handling accepts it)."""
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except ValueError:
            items = [line.strip() for line in items.splitlines() if line.strip()]
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
        kind = "complete" if _complete(new) else "new"  # a plan can arrive already done
        return {"items": new, "kind": kind, "changes": [], "progress": progress(new), "retired": retired}
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
    """Steps through a session's plan updates in order. `dismissed`: updates after which you dismissed the plan."""

    def __init__(self, dismissed=()):
        self.items: list[dict] | None = None
        self.dismissed = set(dismissed)
        self.last = ""

    def push(self, raw, tool_use_id: str = "") -> dict:
        event = {"type": "plan", **step(self.items, normalize(raw))}
        self.items = event["items"] or None
        self.last = tool_use_id
        return event

    def dismissal(self) -> dict | None:
        """After the update you dismissed the plan at: it's cleared, as if the model had cleared it."""
        if self.last not in self.dismissed or not self.items:
            return None
        event = {"type": "plan", **step(self.items, []), "dismissed": True}
        self.items = None
        return event


def dismissed_ids(store, sid: str) -> list[str]:
    return list((store.get_session(sid).context_state or {}).get("plan_dismissed", []))


def dismissed_after(store, sid: str) -> dict[str, int]:
    """For each dismissed update: the id of the last message when you dismissed it."""
    return dict((store.get_session(sid).context_state or {}).get("plan_dismissed_after", {}))


def _replay(store, sid: str, calls) -> Tracker:
    tracker = Tracker(dismissed_ids(store, sid))
    for tid, items in calls:
        tracker.push(items, tid)
        tracker.dismissal()
    return tracker


def applied_ids(store, sid: str) -> set[str]:
    """Tool use ids whose result succeeded. A rejected or cancelled update_plan changed nothing, so it isn't part of
    the plan's story."""
    ok = set()
    for _, m in store.messages(sid, include_archived=True):
        for b in m["content"]:
            r = b.get("toolResult")
            if r and r.get("status") != "error":
                ok.add(r.get("toolUseId", ""))
    return ok


def updates(store, sid: str) -> list[tuple[str, object]]:
    """Every update_plan call that took effect, in order (compacted messages included): (tool use id, items)."""
    ok = applied_ids(store, sid)
    out = []
    for _, m in store.messages(sid, include_archived=True):
        for b in m["content"]:
            tu = b.get("toolUse")
            if tu and tu.get("name") == "update_plan" and tu.get("toolUseId") in ok:
                out.append((tu.get("toolUseId", ""), tu.get("input", {}).get("items")))
    return out


def event_for(store, sid: str, tool_use_id: str, raw, pending: list[tuple[str, object]]) -> dict:
    """The event for one update_plan call, given the calls that took effect before it. `pending`: calls made earlier
    in this agent loop, whose results may not be stored yet (several tool calls in one response)."""
    stored = updates(store, sid)
    seen = {tid for tid, _ in stored}
    tracker = _replay(store, sid, stored + [(tid, items) for tid, items in pending if tid not in seen])
    return tracker.push(raw, tool_use_id)


def current(store, sid: str) -> dict:
    """The plan as it stands now (after a rewind, say), as a 'restore' event."""
    items = _replay(store, sid, updates(store, sid)).items or []
    return {"type": "plan", "kind": "restore", "items": items, "changes": [], "progress": progress(items),
            "retired": None}


def dismiss(store, sid: str) -> dict | None:
    """Put away the plan a turn left unfinished. Returns its 'clear' event, or None if no unfinished plan is shown."""
    calls = updates(store, sid)
    tracker = _replay(store, sid, calls)
    if not calls or not tracker.items or _complete(tracker.items):
        return None
    state = dict(store.get_session(sid).context_state or {})
    state["plan_dismissed"] = [*state.get("plan_dismissed", []), calls[-1][0]]
    # Where it happened, for a reload: after the last message so far (a later turn may have worked on the plan).
    state["plan_dismissed_after"] = {**state.get("plan_dismissed_after", {}), calls[-1][0]: store.messages(sid)[-1][0]}
    state["plan_dismissed_told"] = False
    store.update_session(sid, context_state=state)
    tracker.dismissed.add(calls[-1][0])
    return tracker.dismissal()


def dismissal_note(state: dict) -> str | None:
    """For the turn context, once after you dismiss a plan. Updates `state` (the caller saves it)."""
    if not state.get("plan_dismissed") or state.get("plan_dismissed_told", True):
        return None
    state["plan_dismissed_told"] = True
    return ("The user dismissed your plan (update_plan). Don't carry on with its remaining steps unless they ask; if "
            "new multi-step work needs a plan, start a new one.")
