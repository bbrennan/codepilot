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


# -- finding things in every folder (task 2) ------------------------------------------------------------------------


def _git_repo(path):
    import subprocess

    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid")):
        subprocess.run(["git", "-C", str(path), "config", key, value], check=True)


def test_a_search_with_no_folder_given_covers_every_folder(ctx, api):
    from codepilot.tools import search_code

    _git_repo(api)
    (api / ".gitignore").write_text("secret.txt\n")
    (api / "secret.txt").write_text("PORT = 1\n")
    out = search_code(ctx, r"PORT|return a")
    assert f"{(api / 'src' / 'app.py').resolve()}:1: PORT = 8000" in out
    assert "agent/core.py:2:" in out  # the main folder's too
    assert "secret.txt" not in out  # the added folder's own .gitignore is honoured
    only = search_code(ctx, "PORT", str(api))
    assert "app.py" in only and "agent/core.py" not in only


def test_the_python_search_honours_an_added_folders_gitignore(ctx, api, monkeypatch):
    from codepilot import tools

    monkeypatch.setattr(tools.shutil, "which", lambda name: None)  # no ripgrep: the Python engine
    _git_repo(api)
    (api / ".gitignore").write_text("secret.txt\n")
    (api / "secret.txt").write_text("PORT = 1\n")
    out = tools.search_code(ctx, "PORT")
    assert "app.py:1: PORT = 8000" in out and "secret.txt" not in out


def test_go_to_file_and_mentions_find_files_in_added_folders(repo, api):
    from codepilot import mentions

    app = str((api / "src" / "app.py").resolve())
    assert app in mentions.find_files(repo.resolve(), "app.py", 30, added=[api.resolve()])
    assert "agent/core.py" in mentions.find_files(repo.resolve(), "core", 30, added=[api.resolve()])
    [m] = mentions.find_mentions(repo.resolve(), f"look at @{app}", added=[api.resolve()])
    assert m["rel"] == app
    block, labels = mentions.attachment_block(repo.resolve(), f"look at @{app}", added=[api.resolve()])
    assert "PORT = 8000" in block and labels == [app]
    assert mentions.find_mentions(repo.resolve(), f"look at @{app}") == []  # not a session folder: left alone


def test_an_added_folders_steering_is_followed(ctx, api, cfg, store):
    from codepilot.agent import Agent
    from fakes import FakeLLM

    (api / "AGENTS.md").write_text("Use tabs in the API.\n")
    agent = Agent(cfg, store, llm=FakeLLM([]))
    sess = store.get_session(ctx.session_id)
    text = "".join(b.get("text", "") for b in agent._system(sess, agent._ctx(sess)))
    assert "api/AGENTS.md" in text and "Use tabs in the API." in text
    before = agent._session_system(sess, agent._ctx(sess))
    (api / "AGENTS.md").write_text("Use spaces in the API.\n")  # an edit applies from the next request
    after = agent._session_system(store.get_session(ctx.session_id), agent._ctx(sess))
    assert before != after and "Use spaces in the API." in "".join(b.get("text", "") for b in after)


# -- from review (task 2) -------------------------------------------------------------------------------------------


def test_an_image_mentioned_in_an_added_folder_is_attached(repo, api):
    from test_images import PNG

    from codepilot import images

    (api / "shot.png").write_bytes(PNG)
    found, problems = images.from_message(f"what's wrong here? @{api.resolve()}/shot.png", repo.resolve(),
                                          added=[api.resolve()])
    assert len(found) == 1 and problems == []


def test_an_added_folders_files_get_its_own_file_steering_not_the_main_folders(ctx, api, cfg, store):
    from codepilot.agent import Agent
    from fakes import FakeLLM

    for folder, rule in ((ctx.root, "Main folder Python rule."), (api, "API Python rule.")):
        (folder / ".codepilot" / "steering").mkdir(parents=True, exist_ok=True)
        (folder / ".codepilot" / "steering" / "py.md").write_text(
            f"---\ninclusion: fileMatch\nfileMatchPattern: 'src/*.py'\n---\n{rule}\n")
    (ctx.root / "src").mkdir()
    (ctx.root / "src" / "main.py").write_text("x = 1\n")
    agent = Agent(cfg, store, llm=FakeLLM([]))
    text, _ = agent._message_steering(ctx.session_id, ctx.root, f"look at @{(api / 'src' / 'app.py').resolve()}")
    assert "API Python rule." in text and "Main folder Python rule." not in text
    docs = agent._file_steering(ctx, {"name": "read_file", "input": {"path": "src/main.py"}})
    assert [d.body.strip() for d, _ in docs] == ["Main folder Python rule."]  # the main folder's, as before


def test_a_glob_matches_an_added_folders_paths_without_ripgrep(ctx, api, monkeypatch):
    from codepilot import tools

    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    assert "app.py:1: PORT = 8000" in tools.search_code(ctx, "PORT", glob="src/*.py")


# -- from the release review ----------------------------------------------------------------------------------------


def test_reordering_the_list_cant_slip_a_nested_folder_in(repo, api):
    with pytest.raises(ValueError, match="inside"):
        folders.patch(str(repo), [str(api)], {"folders": [str(api / "src"), str(api)]})
    with pytest.raises(ValueError, match="inside"):
        folders.patch(str(repo), [str(api)], {"folders": [str(api), str(api / "src")]})


def test_a_missing_folder_cant_be_made_main(repo, api, tmp_path):
    gone = tmp_path / "gone"
    with pytest.raises(ValueError, match="doesn't exist"):
        folders.make_main(str(repo), [str(api), str(gone)], str(gone))


def test_steering_from_a_file_codepilot_reads_resolves_in_that_files_folder(ctx, api, cfg, store):
    from codepilot.agent import Agent
    from fakes import FakeLLM

    (api / "docs").mkdir()
    (api / "docs" / "api.md").write_text("The API's own guide.\n")
    (api / ".codepilot" / "steering").mkdir(parents=True)
    (api / ".codepilot" / "steering" / "py.md").write_text(
        "---\ninclusion: fileMatch\nfileMatchPattern: 'src/*.py'\n---\nSee #[[file:docs/api.md]]\n")
    agent = Agent(cfg, store, llm=FakeLLM([]))
    found = agent._file_steering(ctx, {"name": "read_file", "input": {"path": str(api / "src" / "app.py")}})
    [(doc, owner)] = found
    assert owner == api.resolve() and "The API's own guide." in __import__("codepilot.steering").steering.render(doc, owner)


def test_an_added_folders_steering_isnt_mistaken_for_the_main_folders_of_the_same_name(ctx, api, cfg, store):
    from codepilot import steering

    for folder, rule in ((ctx.root, "Main rule."), (api, "API rule.")):
        (folder / ".codepilot" / "steering").mkdir(parents=True, exist_ok=True)
        (folder / ".codepilot" / "steering" / "py.md").write_text(
            f"---\ninclusion: fileMatch\nfileMatchPattern: 'src/*.py'\n---\n{rule}\n")
    (ctx.root / "src").mkdir()
    (ctx.root / "src" / "main.py").write_text("x = 1\n")
    main = steering.for_paths([ctx.root / "src" / "main.py"], ctx.root, ctx.folders, cfg.home, set())
    loaded = {d.label for d, _ in main}  # the main folder's py.md is loaded first
    other = steering.for_paths([(api / "src" / "app.py").resolve()], ctx.root, ctx.folders, cfg.home, loaded)
    assert [d.body.strip() for d, _ in other] == ["API rule."]
    twin = api.parent / "elsewhere" / "api"  # another added folder with the same name
    assert {d.label for d, _ in other}.isdisjoint({f"{twin}/.codepilot/steering/py.md"})
    assert str(api.resolve()) in next(d.label for d, _ in other)  # identified by its folder, not just its name


def test_existing_failures_with_a_skipped_change_dont_read_as_passed(ctx, api, cfg, tmp_path):
    from dataclasses import asdict, replace

    from codepilot import verification

    propose_edit(ctx, str(api / "src" / "app.py"), "PORT = 8000", "PORT = 9000")
    receipt = verification.verify(ctx.root, replace(cfg, test_cmd="sh -c 'echo FAILED tests/test_x.py::test_old; exit 1'"), ctx.store.list_proposals(ctx.session_id),
                                  workdir=tmp_path / "work", analysers=False)
    text = verification.describe(asdict(receipt))
    assert receipt.status == "partial" and "passed" not in text.split("\n")[0] and "no new failures" in text


def test_a_file_dropped_into_an_added_folder_lands_there(ctx, api):
    from codepilot import uploads

    out = uploads.store_upload(ctx, str(api.resolve() / "src" / "notes.txt"), b"hi")
    assert (api / "src" / "notes.txt").read_bytes() == b"hi" and out
    _git_repo(api)
    with pytest.raises(uploads.UploadError, match=".git"):
        uploads.store_upload(ctx, str(api.resolve() / ".git" / "config2"), b"x")  # its own .git stays protected


# -- from the final release review ----------------------------------------------------------------------------------


def test_changing_the_main_folder_and_the_added_ones_at_once_is_refused(repo, api):
    with pytest.raises(ValueError, match="separately"):
        folders.patch(str(repo), [], {"repo": str(api), "folders": [str(api)]})


def test_a_rename_in_either_status_column_skips_its_old_name():
    out = " R new.py\0old.py\0R  moved.py\0was.py\0?? my file é.py\0"
    assert folders.git_status(out) == [{"path": "new.py", "code": "R"}, {"path": "moved.py", "code": "R"},
                                       {"path": "my file é.py", "code": "??"}]


def test_list_files_matches_a_pattern_in_an_added_folder(ctx, api):
    assert str((api / "src" / "app.py").resolve()) in list_files(ctx, str(api), pattern="src/*.py")
