"""Verification receipts: pending changes are tested on a disposable copy of the workspace before review."""

import hashlib
import subprocess
import sys

from codepilot import verification


def snapshot(root):
    """Every file under root (including .git) and its hash, to prove the workspace was never touched."""
    return {str(p.relative_to(root)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


def pending(store, sid, path, old, new):
    return store.add_proposal(sid, path, old, new, "")


def test_clone_tree_copies_everything_and_the_copy_is_independent(repo, tmp_path):
    (repo / ".hidden").write_text("dot file\n")
    dst = tmp_path / "copy"
    verification.clone_tree(repo, dst)
    assert snapshot(dst) == snapshot(repo) and (dst / ".git").is_dir()
    (dst / "agent/core.py").write_text("changed in the copy\n")
    assert "a - b" in (repo / "agent/core.py").read_text()


def _fake_venv(root, binary_marker):
    venv = root / ".venv"
    (venv / "bin").mkdir(parents=True)
    site = venv / "lib/python3.11/site-packages"
    (site / "pkg-1.0.dist-info").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    (venv / "bin/pytest").write_text(f"#!{root}/.venv/bin/python\nimport pytest\n")
    (venv / "bin/blob").write_bytes(b"\0\1\2" + binary_marker)
    (site / "__editable___pkg_1_0_finder.py").write_text(f"MAPPING = {{'pkg': '{root}/pkg'}}\n")
    (site / "__editable__.pkg-1.0.pth").write_text(f"{root}/src\n")
    (site / "pkg-1.0.dist-info/direct_url.json").write_text(f'{{"url": "file://{root}"}}')
    return venv


def test_relocate_envs_points_a_copied_virtualenv_at_the_copy(tmp_path):
    src, dst = tmp_path / "ws", tmp_path / "copy"
    src.mkdir()
    _fake_venv(src, str(tmp_path / "ws").encode())
    verification.clone_tree(src, dst)
    assert verification.relocate_envs(src, dst) == []
    venv, site = dst / ".venv", dst / ".venv/lib/python3.11/site-packages"
    assert (venv / "bin/pytest").read_text().startswith(f"#!{dst}/.venv/bin/python\n")
    assert f"'{dst}/pkg'" in (site / "__editable___pkg_1_0_finder.py").read_text()
    assert (site / "__editable__.pkg-1.0.pth").read_text() == f"{dst}/src\n"
    assert f"file://{dst}" in (site / "pkg-1.0.dist-info/direct_url.json").read_text()
    assert (venv / "bin/blob").read_bytes() == (src / ".venv/bin/blob").read_bytes()  # binaries are left alone
    assert f"{src}/.venv" in (src / ".venv/bin/pytest").read_text()  # the workspace's own venv is untouched


def test_relocate_envs_reports_files_it_could_not_rewrite(tmp_path):
    src, dst = tmp_path / "ws", tmp_path / "copy"
    src.mkdir()
    _fake_venv(src, b"")
    verification.clone_tree(src, dst)
    stuck = dst / ".venv/bin/pytest"
    stuck.chmod(0o444)
    try:
        assert verification.relocate_envs(src, dst) == [".venv/bin/pytest"]
    finally:
        stuck.chmod(0o644)


def test_a_copied_real_virtualenv_runs_the_copys_code(tmp_path):
    src, dst = tmp_path / "ws", tmp_path / "copy"
    (src / "pkgdir").mkdir(parents=True)
    (src / "pkgdir/mod.py").write_text("VALUE = 'workspace'\n")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(src / ".venv")], check=True)
    site = next((src / ".venv").glob("lib/python*/site-packages"))
    (site / "ws.pth").write_text(f"{src}/pkgdir\n")  # what an editable install does
    verification.clone_tree(src, dst)
    (dst / "pkgdir/mod.py").write_text("VALUE = 'copy'\n")
    run = [str(dst / ".venv/bin/python"), "-c", "import mod; print(mod.VALUE)"]
    assert subprocess.run(run, capture_output=True, text=True).stdout.strip() == "workspace"  # the trap
    assert verification.relocate_envs(src, dst) == []
    assert subprocess.run(run, capture_output=True, text=True).stdout.strip() == "copy"


def test_fingerprint_changes_with_the_pending_set(store, repo):
    sid = store.create_session(str(repo), "main").id
    one = pending(store, sid, "agent/core.py", "a - b", "a + b")
    two = pending(store, sid, "tests/test_core.py", "== 3", "== 3  # ok")
    base = verification.fingerprint([one, two])
    assert verification.fingerprint([two, one]) == base  # order of the list doesn't matter
    assert verification.fingerprint([one]) != base
    other = pending(store, sid, "agent/core.py", "a - b", "b + a")
    assert verification.fingerprint([other, two]) != base


def test_prepare_applies_pending_changes_to_a_copy_and_never_touches_the_workspace(store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    created = pending(store, sid, "agent/extra.py", "", "x = 1\n")
    before = snapshot(repo)
    with verification.prepared(repo, [created, fix], tmp_path / "work") as copy:
        assert copy.path.is_dir() and copy.conflict == "" and copy.isolation == []
        assert "a + b" in (copy.path / "agent/core.py").read_text() and (copy.path / "agent/extra.py").exists()
        assert copy.originals == {"agent/core.py": "def add(a, b):\n    return a - b\n", "agent/extra.py": None}
        where = copy.path
    assert not where.exists()  # removed afterwards
    assert snapshot(repo) == before


def test_prepare_reports_changes_that_cannot_be_combined(store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    first = pending(store, sid, "agent/core.py", "a - b", "a + b")
    clash = pending(store, sid, "agent/core.py", "return a - b", "return b - a")  # no longer applies after #1
    with verification.prepared(repo, [first, clash], tmp_path / "work") as copy:
        assert copy.conflict == f"#{clash.id} (agent/core.py) no longer applies after the earlier changes"


def test_prepare_removes_the_copy_even_when_the_caller_fails(store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    where = None
    try:
        with verification.prepared(repo, [fix], tmp_path / "work") as copy:
            where = copy.path
            raise RuntimeError("tests blew up")
    except RuntimeError:
        pass
    assert where is not None and not where.exists()


# -- running the checks -------------------------------------------------------------------------------------------

def pytest_cfg(cfg):
    from dataclasses import replace
    return replace(cfg, test_cmd=f"{sys.executable} -m pytest -q -p no:cacheprovider")


def test_verify_runs_the_real_tests_against_the_changes(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")  # the sample repo's test fails until this lands
    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "work", analysers=False)
    assert receipt.status == "pass" and receipt.proposal_ids == [fix.id] and receipt.newly_failing == []
    assert [(r.name, r.exit, r.baseline_exit) for r in receipt.runs] == [("tests", 0, None)]
    assert "1 passed" in receipt.runs[0].output and receipt.fingerprint == verification.fingerprint([fix])


def test_verify_names_tests_the_changes_newly_break(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    (repo / "tests/test_more.py").write_text("from agent.core import add\n\ndef test_zero():\n    assert add(0, 0) == 0\n")
    breaks = pending(store, sid, "agent/core.py", "a - b", "a - b + 1")
    receipt = verification.verify(repo, pytest_cfg(cfg), [breaks], workdir=tmp_path / "work", analysers=False)
    assert receipt.status == "fail" and receipt.runs[0].exit == 1 and receipt.runs[0].baseline_exit == 1
    assert receipt.newly_failing == ["tests: tests/test_more.py::test_zero"]  # test_add was already failing
    assert "a - b\n" in (repo / "agent/core.py").read_text()


def fake_runner(results):
    """A runner that answers from the copy's files: results maps a command name to fn(copy) -> (exit, output)."""
    calls = []

    def run(argv, cwd, timeout, env=None):
        name = "tests" if "pytest" in " ".join(argv) else argv[0].rsplit("/", 1)[-1]
        calls.append((name, (cwd / "agent/core.py").read_text() if (cwd / "agent/core.py").exists() else None))
        return results[name](cwd)
    run.calls = calls
    return run


def test_only_failures_get_a_baseline_and_already_failing_ones_are_not_blamed(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    run = fake_runner({"tests": lambda cwd: (1, "FAILED tests/test_old.py::test_flaky - boom\n1 failed")})
    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=run, analysers=False)
    assert receipt.status == "preexisting" and receipt.newly_failing == []
    assert [c[1] for c in run.calls] == ["def add(a, b):\n    return a + b\n", "def add(a, b):\n    return a - b\n"]


def test_newly_failing_parsers():
    nf = verification.newly_failing
    assert nf("tests", "FAILED t.py::a - x\nERROR t.py::b\nFAILED t.py::c", 1, "FAILED t.py::c", 1) == \
        ["tests: t.py::a", "tests: t.py::b"]
    assert nf("tests", "  ✕ adds numbers (3 ms)\n  ✕ old one", 1, "  ✕ old one", 1) == ["tests: adds numbers"]
    assert nf("tests", "--- FAIL: TestAdd (0.00s)\n--- FAIL: TestOld", 1, "--- FAIL: TestOld (0.01s)", 1) == \
        ["tests: TestAdd"]
    assert nf("tests", "something unparseable", 2, "all good", 0) == ["tests: exit 2 (was 0 without the changes)"]
    assert nf("tests", "something unparseable", 2, "still unparseable", 2) == []
    assert nf("ruff", "agent/core.py:3:1: F401 unused import\nagent/core.py:9:5: E711 x", 1,
              "agent/core.py:7:5: E711 x", 1) == ["ruff: agent/core.py: F401 unused import"]


def test_analysers_run_on_the_changed_files_of_the_copy(cfg, store, repo, tmp_path, monkeypatch):
    from codepilot import checks
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    seen = []

    def detect(root, paths=None):
        seen.append((root, paths))
        return [checks.Check("ruff", "lint", ["ruff", "check", *paths])]

    monkeypatch.setattr(verification.checks, "detect", detect)
    run = fake_runner({"tests": lambda cwd: (0, "1 passed"),
                       "ruff": lambda cwd: (1, "agent/core.py:2:5: F821 undefined name")
                       if "a + b" in (cwd / "agent/core.py").read_text() else (0, "")})
    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=run)
    assert seen[0][1] == ["agent/core.py"] and seen[0][0] != repo  # the copy, not the workspace
    assert [r.name for r in receipt.runs] == ["tests", "ruff"] and receipt.status == "fail"
    assert receipt.runs[1].kind == "lint" and receipt.runs[1].baseline_exit == 0
    assert receipt.newly_failing == ["ruff: agent/core.py: F821 undefined name"]


def test_nothing_to_run_is_not_a_pass(cfg, store, repo, tmp_path, monkeypatch):
    from dataclasses import replace
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    monkeypatch.setattr(verification, "detect_test_cmd", lambda root, cfg: "")
    receipt = verification.verify(repo, replace(cfg, test_cmd=""), [fix], workdir=tmp_path / "w", analysers=False)
    assert receipt.status == "nothing" and receipt.runs == []


def test_a_conflict_runs_nothing(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    gone = pending(store, sid, "agent/core.py", "not in the file", "x")
    run = fake_runner({})
    receipt = verification.verify(repo, pytest_cfg(cfg), [gone], workdir=tmp_path / "w", runner=run)
    assert receipt.status == "error" and "no longer applies" in receipt.conflict and run.calls == []


def test_timeout_and_cancel_stop_between_runs(cfg, store, repo, tmp_path, monkeypatch):
    from codepilot import checks
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    monkeypatch.setattr(verification.checks, "detect",
                        lambda root, paths=None: [checks.Check("ruff", "lint", ["ruff", "check"])])
    slow = fake_runner({"tests": lambda cwd: (None, "timed out"), "ruff": lambda cwd: (0, "")})
    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=slow)
    assert receipt.status == "timeout" and [c[0] for c in slow.calls] == ["tests"]
    calls = []
    cancel = fake_runner({"tests": lambda cwd: calls.append(1) or (0, "ok"), "ruff": lambda cwd: (0, "")})
    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=cancel,
                                  cancelled=lambda: bool(calls))
    assert receipt.status == "cancelled" and [c[0] for c in cancel.calls] == ["tests"]
    assert not any((tmp_path / "w").iterdir())  # copies removed either way


def test_a_copy_that_may_run_the_workspace_code_is_never_a_plain_pass(cfg, store, repo, tmp_path, monkeypatch):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    monkeypatch.setattr(verification, "relocate_envs", lambda src, dst: [".venv/bin/pytest"])
    run = fake_runner({"tests": lambda cwd: (0, "1 passed")})
    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=run, analysers=False)
    assert receipt.status == "unverified" and receipt.isolation == [".venv/bin/pytest"]


# -- storing receipts ---------------------------------------------------------------------------------------------

def test_receipts_are_stored_per_session_and_the_latest_wins(cfg, store, repo):
    from codepilot.store import Store
    sid = store.create_session(str(repo), "main").id
    other = store.create_session(str(repo), "main").id
    assert store.latest_receipt(sid) is None
    first = store.add_receipt(sid, {"fingerprint": "f1", "status": "fail", "runs": []})
    second = store.add_receipt(sid, {"fingerprint": "f2", "status": "pass", "runs": []})
    store.add_receipt(other, {"fingerprint": "zz", "status": "error", "runs": []})
    latest = store.latest_receipt(sid)
    assert latest["id"] == second > first and latest["status"] == "pass" and latest["told"] is False
    store.mark_receipt_told(second)
    reopened = Store(cfg.home)  # survives a restart
    assert reopened.latest_receipt(sid)["told"] is True and reopened.latest_receipt(sid)["fingerprint"] == "f2"


def test_an_older_database_gets_the_receipts_table(cfg, store):
    from codepilot.store import Store
    with store._db:
        store._db.execute("DROP TABLE receipts")
    reopened = Store(cfg.home)
    sid = reopened.create_session("", "main").id
    assert reopened.add_receipt(sid, {"fingerprint": "f", "status": "pass", "runs": []}) > 0


# -- review fixes -------------------------------------------------------------------------------------------------

def test_modes_that_run_nothing_cannot_verify():
    from codepilot import modes
    assert "verify_changes" in modes.READ_ONLY_BLOCK
    ask = next(m for m in modes.BUILTIN if m.name == "ask")
    assert "verify_changes" in ask.blocked


def test_a_workspace_containing_the_verification_folder_is_refused(cfg, store, tmp_path):
    from dataclasses import replace
    ws = tmp_path / "home-like"
    (ws / "proj").mkdir(parents=True)
    (ws / "proj/a.py").write_text("x = 1\n")
    sid = store.create_session(str(ws), "main").id
    change = pending(store, sid, "proj/a.py", "x = 1", "x = 2")
    copier_calls = []
    receipt = verification.verify(ws, replace(cfg, home=ws / ".codepilot"), [change],
                                  workdir=ws / ".codepilot/verify/s", copier=lambda s, d: copier_calls.append(d))
    assert receipt.status == "error" and "inside the workspace" in receipt.conflict and copier_calls == []


def test_a_copy_failure_is_an_error_receipt_not_an_exception(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    change = pending(store, sid, "agent/core.py", "a - b", "a + b")

    def broken(src, dst):
        raise OSError("No space left on device")

    receipt = verification.verify(repo, pytest_cfg(cfg), [change], workdir=tmp_path / "w", copier=broken)
    assert receipt.status == "error" and "couldn't copy the workspace: No space left" in receipt.conflict


def test_relocation_never_writes_through_a_link_out_of_the_copy(tmp_path):
    src, dst, elsewhere = tmp_path / "ws", tmp_path / "copy", tmp_path / "shared-venv"
    elsewhere.mkdir()
    _fake_venv(elsewhere, b"")  # makes elsewhere/.venv naming `elsewhere`
    real = elsewhere / ".venv"
    (real / "bin/pytest").write_text(f"#!{src}/.venv/bin/python\n")  # names the workspace
    src.mkdir()
    (src / ".venv").symlink_to(real)  # the workspace's venv lives outside it
    verification.clone_tree(src, dst)
    before = (real / "bin/pytest").read_text()
    stuck = verification.relocate_envs(src, dst)
    assert (real / "bin/pytest").read_text() == before  # the shared environment is untouched
    assert stuck == [".venv (links outside the copy)"]


def test_paths_into_the_workspace_are_rebased_onto_the_copy(tmp_path, monkeypatch):
    ws, copy = tmp_path / "ws", tmp_path / "copy"
    monkeypatch.setenv("PATH", f"{ws}/.venv/bin:/usr/bin")
    env = verification.run_env(ws, copy, tmp_path / "pyc")
    assert env["PATH"].split(":")[0] == f"{copy}/.venv/bin" and "/usr/bin" in env["PATH"]
    assert env["PYTHONPYCACHEPREFIX"] == str(tmp_path / "pyc") and "VIRTUAL_ENV" not in env
    assert verification.rebase_argv([f"{ws}/.venv/bin/pytest", "-q", f"{ws}/tests"], ws, copy) == \
        [f"{copy}/.venv/bin/pytest", "-q", f"{copy}/tests"]


def test_each_run_gets_its_own_bytecode_cache(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    caches = []

    def run(argv, cwd, timeout, env=None):
        caches.append(env["PYTHONPYCACHEPREFIX"])
        return (1, "FAILED tests/test_core.py::test_add")

    verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=run, analysers=False)
    assert len(caches) == 2 and caches[0] != caches[1]


def test_failures_are_compared_on_the_full_output_not_the_tail(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    noise = "x" * 20_000
    after = "FAILED tests/test_new.py::test_regression\n" + noise + "\nFAILED tests/test_old.py::test_flaky\n"

    def run(argv, cwd, timeout, env=None):
        changed = "a + b" in (cwd / "agent/core.py").read_text()
        return (1, after if changed else "FAILED tests/test_old.py::test_flaky\n")

    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=run, analysers=False)
    assert receipt.newly_failing == ["tests: tests/test_new.py::test_regression"] and receipt.status == "fail"
    assert len(receipt.runs[0].output) <= verification.OUTPUT_TAIL


def test_failures_that_cannot_be_told_apart_are_inconclusive_not_green(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    run = fake_runner({"tests": lambda cwd: (2, "build failed: undefined: Foo") if "a + b" in
                       (cwd / "agent/core.py").read_text() else (1, "--- FAIL: TestOld (0.01s)")})
    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=run, analysers=False)
    assert receipt.status == "inconclusive" and receipt.newly_failing == []


def test_a_baseline_timeout_is_a_timeout(cfg, store, repo, tmp_path):
    sid = store.create_session(str(repo), "main").id
    fix = pending(store, sid, "agent/core.py", "a - b", "a + b")
    run = fake_runner({"tests": lambda cwd: (1, "FAILED t.py::a") if "a + b" in (cwd / "agent/core.py").read_text()
                       else (None, "timed out")})
    receipt = verification.verify(repo, pytest_cfg(cfg), [fix], workdir=tmp_path / "w", runner=run, analysers=False)
    assert receipt.status == "timeout" and receipt.newly_failing == []
