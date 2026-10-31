import pytest

from codepilot import traces
from codepilot.tools import (
    ToolContext,
    ToolError,
    apply_proposal,
    build_tools,
    execute,
    git,
    list_files,
    propose_edit,
    read_file,
    search_code,
    search_traces,
    trace_outline,
)


@pytest.fixture
def ctx(repo, cfg, store):
    sess = store.create_session(str(repo), "main")
    return ToolContext(root=repo.resolve(), cfg=cfg, store=store, session_id=sess.id)


def test_paths_cannot_escape_repo(ctx):
    with pytest.raises(ToolError):
        read_file(ctx, "../../etc/passwd")
    with pytest.raises(ToolError):
        read_file(ctx, "/etc/hosts")


def test_list_and_read(ctx):
    files = list_files(ctx, pattern="*.py")
    assert "agent/core.py" in files and "tests/test_core.py" in files
    out = read_file(ctx, "agent/core.py")
    assert "    2      return a - b" in out


def test_search_code(ctx):
    assert "agent/core.py:2:" in search_code(ctx, r"return a\s*-\s*b")
    assert search_code(ctx, "nothing_here_xyz") == "(no matches)"


def test_git_is_read_only(ctx):
    assert "No commits yet" in git(ctx, "status") or "branch" in git(ctx, "status")
    for bad in ("commit -m x", "push", "diff --output=/tmp/x", "-c core.pager=evil log"):
        with pytest.raises(ToolError):
            git(ctx, bad)


def test_propose_and_apply_edit(ctx, repo):
    msg = propose_edit(ctx, "agent/core.py", "return a - b", "return a + b", "fix add")
    assert "Proposed change #1" in msg
    assert ctx.events[0]["proposal"]["diff"].count("+    return a + b") == 1
    assert "a - b" in (repo / "agent/core.py").read_text()  # not written yet
    prop = ctx.store.get_proposal(1)
    apply_proposal(repo.resolve(), prop)
    assert "a + b" in (repo / "agent/core.py").read_text()


def test_propose_edit_validation(ctx):
    with pytest.raises(ToolError, match="not found"):
        propose_edit(ctx, "agent/core.py", "nope", "x")
    with pytest.raises(ToolError, match="does not exist"):
        propose_edit(ctx, "agent/new.py", "something", "x")
    assert "Proposed change" in propose_edit(ctx, "agent/new.py", "", "print('hi')\n")


def test_apply_rejects_stale_proposal(ctx, repo):
    propose_edit(ctx, "agent/core.py", "return a - b", "return a + b")
    (repo / "agent/core.py").write_text("changed\n")
    with pytest.raises(ToolError, match="changed since"):
        apply_proposal(repo.resolve(), ctx.store.get_proposal(1))


def test_trace_outline_finds_spans_and_errors(ctx, repo):
    out = trace_outline(ctx, "traces/journey_1.json")
    assert "spans detected: 2" in out and "error spans: 1" in out
    assert "tool.search_products" in out and "!!" in out
    o = traces.outline(repo / "traces" / "run.jsonl")
    assert o["records"] == 2 and o["errors"] == 1
    assert o["spans"][1]["duration_ms"] == pytest.approx(500)


def test_search_traces(ctx):
    out = search_traces(ctx, "red shoes")
    assert "traces/run.jsonl:2:" in out


def test_to_ms_units():
    assert traces.to_ms(1_700_000_000) == 1_700_000_000_000
    assert traces.to_ms(1_700_000_000_000) == 1_700_000_000_000
    assert traces.to_ms(1_700_000_000_000_000_000) == 1_700_000_000_000
    assert traces.to_ms("2024-01-01T00:00:00Z") == 1_704_067_200_000


def test_execute_validates_arguments(ctx, cfg):
    tools = {t.name: t for t in build_tools(cfg)}
    out, err = execute(tools["read_file"], ctx, {})
    assert err and "missing" in out
    out, err = execute(tools["read_file"], ctx, {"path": "agent/core.py", "bogus": 1})
    assert err and "unknown" in out
    # String numbers (common from small local models) are coerced.
    out, err = execute(tools["read_file"], ctx, {"path": "agent/core.py", "start_line": "2", "end_line": None})
    assert not err and "return a - b" in out
    out, err = execute(tools["read_file"], ctx, {"path": "agent/core.py", "start_line": "two"})
    assert err and "bad argument" in out
    # Arrays sent as JSON strings (seen from llama3.2 in the UI) are parsed, not iterated per character.
    out, err = execute(tools["update_plan"], ctx, {"items": '["Read catalog.py", "Check filtering"]'})
    assert not err and ctx.events[-1]["items"] == [{"text": "Read catalog.py", "status": "todo"},
                                                   {"text": "Check filtering", "status": "todo"}]


def test_run_tests_needs_approval_by_default(cfg):
    tools = {t.name: t for t in build_tools(cfg)}
    assert tools["run_tests"].needs_approval and tools["run_command"].needs_approval
    assert tools["open_workspace"].needs_approval
    assert "cloudwatch_logs" not in tools


def test_detect_test_cmd(tmp_path, cfg):
    from dataclasses import replace

    from codepilot.tools import detect_test_cmd

    cfg = replace(cfg, test_cmd="")
    assert detect_test_cmd(tmp_path, cfg) == ""
    (tmp_path / "package.json").write_text("{}")
    assert detect_test_cmd(tmp_path, cfg) == "npm test --silent"
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "uv.lock").write_text("")
    assert detect_test_cmd(tmp_path, cfg) == "uv run pytest -q"
    assert detect_test_cmd(tmp_path, replace(cfg, test_cmd="make check")) == "make check"


def test_run_command_uses_shell_in_workspace(ctx):
    from codepilot.tools import run_command

    out = run_command(ctx, "ls agent | wc -l")
    assert "exit code 0" in out and out.strip().endswith("1")


def test_skills_and_project_instructions(repo, cfg):
    from codepilot import skills

    names = {s.name for s in skills.discover(repo, cfg.home)}
    assert {"code-review", "diagnose-bug", "tdd", "plan-feature", "agent-trace-triage", "grill"} <= names
    custom = repo / ".claude" / "skills" / "deploy"
    custom.mkdir(parents=True)
    (custom / "SKILL.md").write_text("---\nname: deploy\ndescription: How we deploy\n---\nRun make deploy.\n")
    found = skills.find("deploy", repo, cfg.home)
    assert found.description == "How we deploy" and found.body == "Run make deploy."
    assert skills.project_instructions(repo) == ""
    (repo / "AGENTS.md").write_text("Use tabs.")
    (repo / ".kiro" / "steering").mkdir(parents=True)
    (repo / ".kiro" / "steering" / "style.md").write_text("Be terse.")
    text = skills.project_instructions(repo)
    assert "## AGENTS.md\nUse tabs." in text and "## .kiro/steering/style.md\nBe terse." in text


def test_user_only_skills_and_slash(repo, cfg, ctx):
    from codepilot import skills
    from codepilot.tools import load_skill

    grill = skills.find("grill", repo, cfg.home)
    assert grill.user_only and not skills.find("tdd", repo, cfg.home).user_only
    skill, rest = skills.slash_command("/grill the caching design", repo, cfg.home)
    assert skill.name == "grill" and rest == "the caching design"
    assert skills.slash_command("/nonexistent thing", repo, cfg.home) is None
    assert skills.slash_command("not /grill", repo, cfg.home) is None
    with pytest.raises(ToolError, match="user-invoked"):
        load_skill(ctx, "grill")
    assert "feedback loop" in load_skill(ctx, "diagnose-bug")
    # skills installed by `npx skills add` into .agents/skills are picked up
    (repo / ".agents" / "skills" / "team-style").mkdir(parents=True)
    skill_md = repo / ".agents" / "skills" / "team-style" / "SKILL.md"
    skill_md.write_text("---\nname: team-style\ndescription: d\n---\nx")
    assert skills.find("team-style", repo, cfg.home) is not None


def test_write_scratch_stays_in_scratch(ctx, cfg):
    from codepilot.tools import write_scratch

    out = write_scratch(ctx, "repro.py", "print('hi')")
    path = cfg.home / "scratch" / ctx.session_id / "repro.py"
    assert path.read_text() == "print('hi')" and str(path.resolve()) in out
    with pytest.raises(ToolError):
        write_scratch(ctx, "../../escape.py", "x")


def test_apply_then_revert(ctx, repo):
    from codepilot.tools import revert_proposal

    propose_edit(ctx, "agent/core.py", "return a - b", "return a + b")
    before, after = apply_proposal(repo.resolve(), ctx.store.get_proposal(1))
    ctx.store.record_applied(1, before, after)
    revert_proposal(repo.resolve(), ctx.store.get_proposal(1))
    assert "a - b" in (repo / "agent/core.py").read_text()
    # created files are deleted on revert; edited-since files are refused
    propose_edit(ctx, "agent/new.py", "", "x = 1\n")
    before, after = apply_proposal(repo.resolve(), ctx.store.get_proposal(2))
    ctx.store.record_applied(2, before, after)
    (repo / "agent/new.py").write_text("x = 2\n")
    with pytest.raises(ToolError, match="changed since"):
        revert_proposal(repo.resolve(), ctx.store.get_proposal(2))


def test_repo_map(repo):
    from codepilot import repomap

    (repo / "agent" / "svc.ts").write_text("export class Cart {}\nexport async function checkout(cart) {}\n")
    (repo / "agent" / "deep.py").write_text(
        "class Store:\n    def get(self, key, default=None):\n        pass\n"
        "    def _private(self):\n        pass\n\ndef helper(*args, **kw):\n    pass\n")
    repomap._cache.clear()
    m = repomap.build(repo.resolve())
    assert "agent/core.py\n  1: def add(a, b)" in m
    assert "2:   .get(key, default)" in m and "_private" not in m and "7: def helper(*args, **kw)" in m
    assert "1: class Cart" in m and "2: function checkout" in m
    assert m.index("agent/core.py") < m.index("tests/test_core.py")  # sources before tests


def test_unified_diff_without_trailing_newline():
    from codepilot.tools import unified_diff

    d = unified_diff("x.py", 'p > m', 'p <= m')
    assert d.splitlines()[-2:] == ["-p > m", "+p <= m"]


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


@pytest.mark.parametrize("args", [
    "branch -D keep", "branch -d keep", "branch --delete keep", "branch -m keep other", "branch -M x",
    "branch new-one", "branch -f keep HEAD", "branch -vD keep", "branch --set-upstream-to=origin/x",
    "branch -u origin/x", "branch --unset-upstream", "branch --edit-description",
    "stash", "stash drop", "stash pop", "stash clear", "remote add evil https://x", "remote remove origin",
    "reflog expire --all", "reflog delete HEAD@{0}",
    "branch --abbrev -D --abbrev keep", "branch -l new-one", "branch --contains -D keep", "branch --sort -D keep",
    "remote -v remove origin", "remote --verbose set-url origin https://x", "remote -v add evil https://x",
])
def test_read_only_git_refuses_anything_that_writes(ctx, repo, args):
    _git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    _git(repo, "branch", "keep")
    _git(repo, "remote", "add", "origin", "https://example.invalid/r.git")
    with pytest.raises(ToolError, match="read-only|changes|creates|only `git"):  # refused, not a git error
        git(ctx, args)
    assert "keep" in _git(repo, "branch") and "example.invalid/r.git" in _git(repo, "remote", "-v")
    assert "new-one" not in _git(repo, "branch")


@pytest.mark.parametrize("args", [
    "branch", "branch -a", "branch -vv", "branch --show-current", "branch --list 'fe*'", "branch --merged HEAD",
    "branch --contains HEAD", "stash list", "remote -v", "reflog -5", "rev-list --count HEAD",
    "merge-base HEAD HEAD",
])
def test_read_only_git_still_answers_questions(ctx, repo, args):
    _git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    git(ctx, args)  # no ToolError


def test_the_agent_is_told_how_git_writes_work():
    from codepilot import prompts
    text = " ".join(prompts.STATIC.split())
    assert "git tool only reads" in text and "only when the user asks" in text
    assert "stage files by name" in text and "never use -i" in text and "--force" in text


# -- package guard on proposals -----------------------------------------------------------------------------------

def _pypi_404(monkeypatch):
    from codepilot import deps_guard

    def get(url, timeout):
        raise deps_guard.NotFound

    monkeypatch.setattr(deps_guard, "_get", get)


def test_a_manifest_proposal_is_checked_and_tells_the_agent(ctx, repo, monkeypatch):
    _pypi_404(monkeypatch)
    msg = propose_edit(ctx, "pyproject.toml", "", '[project]\ndependencies = ["reqeusts"]\n', "add it")
    assert "`reqeusts` is not on PyPI" in msg and "check the name" in msg
    view = ctx.events[-1]["proposal"]
    assert view["advice"] == [{"eco": "pypi", "name": "reqeusts", "level": "danger",
                               "text": "not on PyPI: possibly an invented name, or a private package"}]


def test_advice_is_kept_with_the_proposal(ctx, repo, cfg, monkeypatch):
    from codepilot.store import Store
    _pypi_404(monkeypatch)
    propose_edit(ctx, "requirements.txt", "", "reqeusts\n", "")
    assert Store(cfg.home).get_proposal(1).advice[0]["name"] == "reqeusts"


def test_other_files_arent_checked(ctx, repo, monkeypatch):
    from codepilot import deps_guard
    calls = []
    monkeypatch.setattr(deps_guard, "_get", lambda url, timeout: calls.append(url) or "{}")
    msg = propose_edit(ctx, "agent/core.py", "a - b", "a + b", "")
    assert "not on" not in msg and calls == [] and ctx.events[-1]["proposal"]["advice"] == []


def test_an_applied_manifest_change_warns_too(ctx, repo, cfg, monkeypatch):
    from dataclasses import replace
    _pypi_404(monkeypatch)
    ctx.cfg = replace(cfg, auto_apply_edits=True)
    msg = propose_edit(ctx, "requirements.txt", "", "reqeusts\n", "")
    assert "Applied change" in msg and "`reqeusts` is not on PyPI" in msg
