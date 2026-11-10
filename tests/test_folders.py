"""Several folders in a session (spec multi-folder): a main folder plus folders you add, saved with the session.
codepilot names files in an added folder by their full path; everything outside every folder stays refused."""

import pytest

from codepilot import checkpoints, folders, prompts
from codepilot.store import Store
from codepilot.tools import ToolContext, ToolError, apply_proposal, list_files, propose_edit, read_file, revert_proposal


@pytest.fixture
def api(tmp_path):
    """A second repo, next to the main one."""
    root = tmp_path / "api"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("PORT = 8000\n")
    return root


@pytest.fixture
def ctx(repo, api, cfg, store):
    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, folders=[str(api)])
    return ToolContext(root=repo.resolve(), cfg=cfg, store=store, session_id=sess.id, folders=[api.resolve()])


# -- the session keeps them -----------------------------------------------------------------------------------------


def test_a_session_keeps_its_added_folders(cfg, store, repo, api):
    sess = store.create_session(str(repo), "main")
    assert store.get_session(sess.id).folders == [] and sess.public()["folders"] == []
    store.update_session(sess.id, folders=[str(api)])
    again = Store(cfg.home).get_session(sess.id)  # after a restart
    assert again.folders == [str(api)] and again.public()["folders"] == [str(api)]


def test_a_folder_to_add_must_be_a_new_directory(repo, api, tmp_path):
    assert folders.check(str(api), repo, []) == api.resolve()
    for path, why in [(tmp_path / "missing", "doesn't exist"), (api / "src" / "app.py", "isn't a folder"),
                      (repo, "already"), (repo / "agent", "inside"), (tmp_path, "contains")]:
        with pytest.raises(ValueError, match=why):
            folders.check(str(path), repo, [])
    for path, why in [(api, "already"), (api / "src", "inside")]:
        with pytest.raises(ValueError, match=why):
            folders.check(str(path), repo, [api])


def test_making_an_added_folder_main_swaps_them(repo, api, tmp_path):
    assert folders.make_main(str(repo), [str(api)], str(api)) == (str(api.resolve()), [str(repo.resolve())])
    with pytest.raises(ValueError, match="isn't one of this session's folders"):
        folders.make_main(str(repo), [str(api)], str(tmp_path))


# -- codepilot's tools reach them ----------------------------------------------------------------------------------


def test_a_file_in_an_added_folder_is_named_by_its_full_path(ctx, api, tmp_path):
    app = (api / "src" / "app.py").resolve()
    assert ctx.resolve(str(app)) == app and ctx.rel(app) == str(app)
    assert ctx.rel(ctx.resolve("agent/core.py")) == "agent/core.py"  # relative paths are still the main folder's
    (tmp_path / "elsewhere.txt").write_text("secret")
    with pytest.raises(ToolError, match="outside"):
        ctx.resolve(str(tmp_path / "elsewhere.txt"))  # outside every folder: refused, as before
    with pytest.raises(ToolError, match="outside"):
        ctx.resolve(str(api / ".." / "elsewhere.txt"))


def test_codepilot_reads_and_lists_an_added_folder(ctx, api):
    assert "PORT = 8000" in read_file(ctx, str(api / "src" / "app.py"))
    assert str((api / "src" / "app.py").resolve()) in list_files(ctx, str(api))


def test_a_change_in_an_added_folder_applies_and_undoes(ctx, api):
    app = api / "src" / "app.py"
    propose_edit(ctx, str(app), "PORT = 8000", "PORT = 9000")
    prop = ctx.store.get_proposal(1)
    assert prop.path == str(app.resolve())
    before, after = apply_proposal(ctx.root, prop, ctx.folders)
    assert app.read_text() == "PORT = 9000\n"
    ctx.store.record_applied(1, before, after)
    applied = ctx.store.get_proposal(1)
    assert checkpoints.preview(ctx.root, [applied], folders=ctx.folders)[0].ok
    revert_proposal(ctx.root, applied, ctx.folders)
    assert app.read_text() == "PORT = 8000\n"


def test_a_change_outside_the_session_folders_still_cannot_apply(ctx, api):
    propose_edit(ctx, str(api / "src" / "app.py"), "PORT = 8000", "PORT = 9000")
    with pytest.raises(ToolError, match="outside"):
        apply_proposal(ctx.root, ctx.store.get_proposal(1))  # the folder was removed from the session since
    assert not checkpoints.preview(ctx.root, [ctx.store.get_proposal(1)])[0].ok


def test_the_system_prompt_names_the_folders(repo, api):
    text = "".join(b.get("text", "") for b in prompts.build_system(
        repo, "", "", [], [], "", "", [], [], "", folders=[api]))
    assert str(api) in text and "full path" in text
    alone = "".join(b.get("text", "") for b in prompts.build_system(repo, "", "", [], [], "", "", [], [], ""))
    assert "Added folders" not in alone


def test_verifying_leaves_a_change_in_an_added_folder_alone(ctx, api, tmp_path):
    """Verification runs the main folder's tests in a copy of it; a change in an added folder isn't in that copy, so it
    must neither count as a conflict nor touch the real file."""
    from codepilot import verification

    propose_edit(ctx, str(api / "src" / "app.py"), "PORT = 8000", "PORT = 9000")
    propose_edit(ctx, "agent/core.py", "return a - b", "return a + b")
    with verification.prepared(ctx.root, ctx.store.list_proposals(ctx.session_id), tmp_path / "work") as copy:
        assert not copy.conflict
        assert "a + b" in (copy.path / "agent" / "core.py").read_text()
    assert (api / "src" / "app.py").read_text() == "PORT = 8000\n"


def test_verifying_with_a_change_in_an_added_folder_is_only_partly_verified(ctx, api, cfg, tmp_path):
    from dataclasses import replace

    from codepilot import verification

    propose_edit(ctx, str(api / "src" / "app.py"), "PORT = 8000", "PORT = 9000")
    propose_edit(ctx, "agent/core.py", "return a - b", "return a + b")
    pending = ctx.store.list_proposals(ctx.session_id)
    ok = replace(cfg, test_cmd="true")
    receipt = verification.verify(ctx.root, ok, pending, workdir=tmp_path / "work", analysers=False)
    assert receipt.status == "partial" and receipt.skipped == [1] and receipt.proposal_ids == [1, 2]
    text = verification.describe(__import__("dataclasses").asdict(receipt))
    assert "#1" in text and "added folder" in text and "not verified" in text
