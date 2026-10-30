"""Turn checkpoints: the changes codepilot applied from a message onwards, and undoing them together.

A checkpoint isn't a snapshot. Every applied proposal keeps its before/after text, so a turn's checkpoint is the
list of proposals applied at or after the message that started it, and restoring it reverts them newest first
with the same guard as Undo. Files changed by commands, the terminal or other editors were never tracked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .store import Proposal, Store
from .tools import ToolError, revert_proposal

CHANGED = "changed since it was applied"
BLOCKED = "a newer change to this file can't be undone"
GONE = "no longer applied"
OUTSIDE = "outside the repository"
LISTED = "left as it was listed"


@dataclass
class Item:
    proposal: Proposal
    ok: bool  # can be undone now
    reason: str = ""


class RestoreError(Exception):
    """Undoing stopped partway: some changes were undone, the rest weren't."""

    def __init__(self, reverted: list[Proposal], left: list[Item], cause: Exception):
        super().__init__(str(cause))
        self.reverted, self.left = reverted, left


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except FileNotFoundError:
        return None


def since(store: Store, sid: str, mid: int) -> list[Proposal]:
    """Applied changes made at or after message `mid`, newest first. [] if the session has no such message."""
    created = store.message_created(mid, sid)
    return [] if created is None else store.applied_since(sid, created)


def newest_applied_first(proposals: list[Proposal]) -> list[Proposal]:
    return sorted(proposals, key=lambda p: (p.applied_at or 0, p.id), reverse=True)


def _inside(root: Path, rel: str) -> bool:
    target = (root / rel).resolve()  # follows symlinks, so a link out of the repository counts as outside
    return target == root or root in target.parents


def preview(root: Path, proposals: list[Proposal], read=_read, hold: frozenset[int] = frozenset()) -> list[Item]:
    """Which of these applied changes (most recently applied first) can be undone now, without writing anything.
    `hold`: ids to leave alone whatever their state (the user saw them listed as left).

    Per file, the newest change must find exactly what it wrote; undoing it would leave its before-text, which
    the next older change must then find, and so on. Once one can't be undone, older ones to that file can't
    either, since they'd overwrite the newer edit.
    """
    root = root.resolve()
    expected: dict[str, str | None] = {}
    stuck: set[str] = set()
    items = []

    def leave(p: Proposal, reason: str) -> None:
        stuck.add(p.path)
        items.append(Item(p, False, reason))

    for p in proposals:
        if p.path in stuck:
            items.append(Item(p, False, BLOCKED))
            continue
        if p.status != "applied" or p.after_text is None:  # e.g. already undone: it doesn't block older ones
            items.append(Item(p, False, GONE))
            continue
        if p.path not in expected and not _inside(root, p.path):
            leave(p, OUTSIDE)
            continue
        try:
            current = expected[p.path] if p.path in expected else read(root / p.path)
        except (OSError, UnicodeDecodeError) as exc:
            leave(p, f"can't be read: {exc}")
            continue
        if current != p.after_text:
            leave(p, CHANGED)
            continue
        if p.id in hold:
            leave(p, LISTED)
            continue
        expected[p.path] = p.before_text
        items.append(Item(p, True))
    return items


def restore(root: Path, store: Store, sid: str, ids: list[int], revert=revert_proposal, keep: list[int] = ()
            ) -> tuple[list[Proposal], list[Item]]:
    """Undo exactly these changes of this session (the ones the user confirmed), most recently applied first.
    `keep`: changes the user saw listed as left; they're reported, never undone.

    Re-checks the disk first, so a change that can't be undone any more is left, not forced. Returns (undone,
    left); raises RestoreError if a write fails partway.
    """
    proposals = []
    for pid in set(ids) | set(keep):
        try:
            p = store.get_proposal(pid)
        except KeyError:
            continue
        if p.session_id == sid:
            proposals.append(p)
    items = preview(root, newest_applied_first(proposals), hold=frozenset(keep) - set(ids))
    reverted: list[Proposal] = []
    for n, item in enumerate(items):
        if not item.ok:
            continue
        try:
            revert(root, item.proposal)
        except (OSError, ToolError) as exc:
            left = [i for i in items[n:] if i.ok] + [i for i in items if not i.ok]
            raise RestoreError(reverted, left, exc) from exc
        store.set_proposal_status(item.proposal.id, "reverted")
        reverted.append(store.get_proposal(item.proposal.id))
    return reverted, [i for i in items if not i.ok]


def _names(proposals: list[Proposal]) -> str:
    return ", ".join(dict.fromkeys(p.path for p in proposals))


def summary(reverted: list[Proposal], left: list[Item]) -> str:
    """One line for the chat after undoing."""
    n = len(reverted)
    text = f"Undid {n} file change{'s' if n != 1 else ''}" + (f" ({_names(reverted)})" if n else "")
    if left:
        text += f"; left {len(left)} as is: " + "; ".join(f"{i.proposal.path} #{i.proposal.id} ({i.reason})"
                                                        for i in left)
    return text + "."


def failure(exc: RestoreError) -> str:
    total = len(exc.reverted) + len([i for i in exc.left if i.ok])
    stuck = next((i.proposal.path for i in exc.left if i.ok), "")
    return (f"Undid {len(exc.reverted)} of {total} file changes, then couldn't undo {stuck}: {exc}. "
            "The conversation wasn't rewound; undo the rest in Changes, or try again.")
