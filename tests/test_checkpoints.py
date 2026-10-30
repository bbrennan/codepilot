"""Turn checkpoints: which applied changes belong to a turn, and undoing them together."""

from codepilot import checkpoints
from codepilot.tools import apply_proposal


def applied(store, root, sid, path, old, new):
    p = store.add_proposal(sid, path, old, new, "")
    before, after = apply_proposal(root, p)
    store.record_applied(p.id, before, after)
    return store.get_proposal(p.id)


def test_since_lists_changes_applied_at_or_after_the_message_newest_first(store, repo):
    sid = store.create_session(str(repo), "main").id
    store.add_message(sid, "user", [{"text": "first"}])
    applied(store, repo, sid, "agent/core.py", "a - b", "a + b")
    mid = store.add_message(sid, "user", [{"text": "second"}])
    second = applied(store, repo, sid, "agent/core.py", "a + b", "a * b")
    created = applied(store, repo, sid, "agent/new.py", "", "x = 1\n")
    store.add_proposal(sid, "agent/core.py", "a * b", "a / b", "")  # pending: never applied, so not part of it
    rejected = store.add_proposal(sid, "agent/core.py", "a * b", "b * a", "")
    store.set_proposal_status(rejected.id, "rejected")
    assert [p.id for p in checkpoints.since(store, sid, mid)] == [created.id, second.id]


def test_since_is_empty_for_an_unknown_message_or_one_from_another_session(store, repo):
    sid = store.create_session(str(repo), "main").id
    other = store.create_session(str(repo), "main").id
    elsewhere = store.add_message(other, "user", [{"text": "hi"}])
    applied(store, repo, sid, "agent/core.py", "a - b", "a + b")
    assert checkpoints.since(store, sid, 999) == []
    assert checkpoints.since(store, sid, elsewhere) == []


def verdicts(items):
    return [(i.proposal.id, i.ok, i.reason) for i in items]


def test_preview_a_chain_of_changes_to_one_file_and_a_created_file(store, repo):
    sid = store.create_session(str(repo), "main").id
    first = applied(store, repo, sid, "agent/core.py", "a - b", "a + b")
    second = applied(store, repo, sid, "agent/core.py", "a + b", "a * b")
    created = applied(store, repo, sid, "agent/new.py", "", "x = 1\n")
    items = checkpoints.preview(repo, [created, second, first])
    assert verdicts(items) == [(created.id, True, ""), (second.id, True, ""), (first.id, True, "")]


def test_preview_leaves_a_file_changed_since_and_every_older_change_to_it(store, repo):
    sid = store.create_session(str(repo), "main").id
    first = applied(store, repo, sid, "agent/core.py", "a - b", "a + b")
    second = applied(store, repo, sid, "agent/core.py", "a + b", "a * b")
    other = applied(store, repo, sid, "tests/test_core.py", "== 3", "== 3  # 1 + 2")
    (repo / "agent/core.py").write_text("def add(a, b):\n    return a * b  # edited by hand\n")
    items = checkpoints.preview(repo, [other, second, first])
    assert verdicts(items) == [
        (other.id, True, ""),
        (second.id, False, "changed since it was applied"),
        (first.id, False, "a newer change to this file can't be undone"),
    ]


def test_preview_leaves_a_created_file_that_was_deleted_or_recreated(store, repo):
    sid = store.create_session(str(repo), "main").id
    gone = applied(store, repo, sid, "agent/gone.py", "", "x = 1\n")
    redone = applied(store, repo, sid, "agent/redone.py", "", "y = 1\n")
    (repo / "agent/gone.py").unlink()
    (repo / "agent/redone.py").write_text("y = 2\n")
    assert [i.ok for i in checkpoints.preview(repo, [redone, gone])] == [False, False]


def test_preview_skips_a_change_that_is_no_longer_applied_without_blocking_older_ones(store, repo):
    sid = store.create_session(str(repo), "main").id
    first = applied(store, repo, sid, "agent/core.py", "a - b", "a + b")
    second = applied(store, repo, sid, "agent/core.py", "a + b", "a * b")
    (repo / "agent/core.py").write_text(second.before_text)  # what /undo does
    store.set_proposal_status(second.id, "reverted")
    items = checkpoints.preview(repo, [store.get_proposal(second.id), first])
    assert verdicts(items) == [(second.id, False, "no longer applied"), (first.id, True, "")]


def test_restore_undoes_only_the_confirmed_changes_newest_first(store, repo):
    sid = store.create_session(str(repo), "main").id
    original = (repo / "agent/core.py").read_text()
    first = applied(store, repo, sid, "agent/core.py", "a - b", "a + b")
    second = applied(store, repo, sid, "agent/core.py", "a + b", "a * b")
    created = applied(store, repo, sid, "agent/new.py", "", "x = 1\n")
    later = applied(store, repo, sid, "tests/test_core.py", "== 3", "== 3  # 1 + 2")  # applied after the preview
    reverted, left = checkpoints.restore(repo, store, sid, [first.id, created.id, second.id])
    assert [p.id for p in reverted] == [created.id, second.id, first.id] and left == []
    assert (repo / "agent/core.py").read_text() == original and not (repo / "agent/new.py").exists()
    assert "# 1 + 2" in (repo / "tests/test_core.py").read_text()
    assert {p.id: p.status for p in store.list_proposals(sid)} == {
        first.id: "reverted", second.id: "reverted", created.id: "reverted", later.id: "applied"}


def test_restore_ignores_changes_from_another_session(store, repo):
    sid = store.create_session(str(repo), "main").id
    other = store.create_session(str(repo), "main").id
    theirs = applied(store, repo, other, "agent/core.py", "a - b", "a + b")
    reverted, left = checkpoints.restore(repo, store, sid, [theirs.id, 999])
    assert reverted == [] and left == [] and store.get_proposal(theirs.id).status == "applied"


def test_restore_reports_what_it_managed_when_a_write_fails(store, repo):
    sid = store.create_session(str(repo), "main").id
    first = applied(store, repo, sid, "agent/core.py", "a - b", "a + b")
    created = applied(store, repo, sid, "agent/new.py", "", "x = 1\n")
    calls = []

    def revert(root, p):
        calls.append(p.id)
        if p.path == "agent/core.py":
            raise PermissionError("read-only file system")
        (root / p.path).unlink()

    try:
        checkpoints.restore(repo, store, sid, [first.id, created.id], revert=revert)
    except checkpoints.RestoreError as exc:
        assert [p.id for p in exc.reverted] == [created.id]
        assert [i.proposal.id for i in exc.left] == [first.id] and "read-only" in str(exc)
    else:
        raise AssertionError("expected RestoreError")
    assert calls == [created.id, first.id]
    assert store.get_proposal(created.id).status == "reverted" and store.get_proposal(first.id).status == "applied"
