"""Spec-driven development: spec files, phases and approvals, the agent's spec tools, and the endpoints."""

import json

import pytest
from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot import specs
from codepilot.agent import Agent
from codepilot.server import create_app
from codepilot.tools import execute

H = {"X-Codepilot": "1"}
TASKS = """# Implementation plan

- [ ] 1. Add the CSV writer
  - Create report/csv.py with write_csv(rows, path)
  - _Requirements: 1.1, 1.2_
- [x] 2. Wire it into the CLI
  - [-] 2.1 Add the --csv flag
    - _Requirements: 2.1_
  - [ ] 2.2 Document it
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_parse_tasks():
    tasks = specs.parse_tasks(TASKS)
    assert [(t.id, t.status, t.depth) for t in tasks] == [
        ("1", "todo", 0), ("2", "done", 0), ("2.1", "in_progress", 1), ("2.2", "todo", 1)]
    assert tasks[0].requirements == ["1.1", "1.2"] and "report/csv.py" in tasks[0].detail
    unnumbered = specs.parse_tasks("- [ ] first\n  - [ ] nested\n- [x] second\n")
    assert [(t.id, t.title) for t in unnumbered] == [("1", "first"), ("1.1", "nested"), ("2", "second")]


def test_set_task_status_edits_only_that_checkbox(tmp_path):
    path = write(tmp_path / "tasks.md", TASKS)
    specs.set_task_status(path, "2.2", "done")
    specs.set_task_status(path, "1.", "in_progress")
    text = path.read_text()
    assert "- [x] 2.2 Document it" in text and "- [-] 1. Add the CSV writer" in text
    assert text.count("- [x]") == 2 and "_Requirements: 1.1, 1.2_" in text
    with pytest.raises(KeyError):
        specs.set_task_status(path, "9", "done")


def test_only_codepilot_specs_are_listed(repo):
    created = specs.create(repo, "csv-export")
    write(repo / ".kiro/specs/auth-flow/requirements.md", "# Req")  # other tools' specs stay theirs
    write(repo / "specs/001-search/spec.md", "# Spec")
    write(repo / "specs/001-search/tasks.md", "- [ ] 1. Index")
    write(repo / ".codepilot/specs/ROADMAP.md", "# not a spec")
    assert [s.name for s in specs.discover(repo)] == ["csv-export"]
    assert specs.get(repo, "auth-flow") is None and specs.get(repo, "001-search") is None
    found = specs.get(repo, "csv-export")
    assert found.phase == "requirements" and found.doc("requirements").name == "requirements.md"
    assert "source" not in found.info(repo)
    assert created.doc("requirements").name == "requirements.md"
    assert specs.create(repo, "bad-login", "bugfix").doc("requirements").name == "bugfix.md"


def test_a_spec_named_like_another_tools_spec_can_be_created(repo):
    write(repo / ".kiro/specs/auth-flow/requirements.md", "# Req")
    assert specs.create(repo, "auth-flow").folder == repo / ".codepilot/specs/auth-flow"


def test_approvals_go_in_order_and_never_backwards(repo):
    spec = specs.create(repo, "csv-export")
    with pytest.raises(ValueError, match="hasn't been written"):
        specs.approve(repo, spec, "requirements")  # not written yet
    write(spec.doc("requirements"), "# R")
    with pytest.raises(ValueError):
        specs.approve(repo, spec, "design")  # can't skip ahead
    spec = specs.approve(repo, spec, "requirements")
    assert spec.phase == "design"
    write(spec.doc("design"), "# D")
    spec = specs.approve(repo, spec, "design")
    spec = specs.approve(repo, spec, "requirements")  # re-approving an edited earlier doc
    assert spec.phase == "tasks"


@pytest.mark.parametrize("bad", ["Has Spaces", "../escape", "", "-lead"])
def test_spec_names(repo, bad):
    with pytest.raises(ValueError):
        specs.create(repo, bad)


def test_slug():
    assert specs.slug("I want to add CSV export to the reports page") == "csv-export-reports-page"


# -- the agent --------------------------------------------------------------------------------------


def spec_session(store, repo):
    sess = store.create_session(str(repo), "main")
    store.update_session(sess.id, mode="spec")
    return sess


def sent_text(llm):
    return " ".join(b.get("text", "") for b in llm.calls[-1]["messages"][-1]["content"])


def test_first_message_in_spec_mode_creates_a_spec_and_gets_phase_instructions(cfg, store, repo):
    llm = FakeLLM([[{"text": "questions?"}], [{"text": "ok"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = spec_session(store, repo)
    events = list(agent.chat(sess.id, "Add CSV export to reports"))
    created = next(e for e in events if e["type"] == "spec")
    assert created["name"] == "csv-export-reports" and created["kind"] == "feature"
    assert 'phase="requirements"' in sent_text(llm) and "EARS" in sent_text(llm)
    sess2 = spec_session(store, repo)
    events = list(agent.chat(sess2.id, "Checkout total is wrong for discounts"))
    assert next(e for e in events if e["type"] == "spec")["kind"] == "bugfix"
    assert "BUGFIX ANALYSIS" in sent_text(llm)


def test_spec_tools_follow_the_phases(cfg, store, repo):
    llm = FakeLLM([
        [tool_use("t1", "write_spec", doc="design", content="too early")],
        [tool_use("t2", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
        [tool_use("t3", "write_spec", doc="requirements", content="# Requirements\n1.1 WHEN x THEN SHALL y")],
        [{"text": "please review"}],
    ])
    agent = Agent(cfg, store, llm=llm)
    sess = spec_session(store, repo)
    events = list(agent.chat(sess.id, "add csv export"))
    results = [e for e in events if e["type"] == "tool_result"]
    assert results[0]["is_error"] and "approves it before you write design" in results[0]["output"]
    assert results[1]["is_error"] and "code changes wait" in results[1]["output"]
    assert not results[2]["is_error"]
    spec = specs.get(repo, "csv-export")
    assert spec.doc("requirements").read_text().startswith("# Requirements")
    assert any(e["type"] == "spec" and e.get("doc") == "requirements" for e in events)
    assert "a - b" in (repo / "agent/core.py").read_text()


def test_implementation_tracks_tasks_and_attaches_the_spec(cfg, store, repo):
    spec = specs.create(repo, "csv-export")
    for phase, text in (("requirements", "REQ 1.1"), ("design", "DESIGN"), ("tasks", TASKS)):
        write(spec.doc(phase), text)
        spec = specs.approve(repo, spec, phase)
    llm = FakeLLM([[tool_use("t1", "update_task", task="1", status="done")], [{"text": "done"}]])
    agent = Agent(cfg, store, llm=llm)
    sess = spec_session(store, repo)
    agent.store.update_session(sess.id, context_state={"spec": "csv-export"})
    list(agent.chat(sess.id, "Implement task 1 of spec csv-export"))
    first_call = " ".join(b.get("text", "") for b in llm.calls[0]["messages"][-1]["content"])
    assert "IMPLEMENTATION" in first_call and "REQ 1.1" in first_call and "DESIGN" in first_call
    assert specs.get(repo, "csv-export").tasks[0].status == "done"


def test_session_auto_apply_writes_edits_immediately(cfg, store, repo):
    llm = FakeLLM([[tool_use("t1", "propose_edit", path="agent/core.py", old_text="a - b", new_text="a + b")],
                   [{"text": "done"}]])
    agent = Agent(cfg, store, llm=llm)
    client = TestClient(create_app(cfg, store, agent))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    assert client.patch(f"/api/sessions/{sid}", json={"auto_apply": True}, headers=H).json()["auto_apply"]
    list(agent.chat(sid, "fix it"))
    assert "a + b" in (repo / "agent/core.py").read_text()
    assert "Auto-apply is now ON" in " ".join(b.get("text", "") for b in llm.calls[0]["messages"][-1]["content"])


# -- endpoints ----------------------------------------------------------------------------------------


def test_spec_endpoints(cfg, store, repo):
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    r = client.post(f"/api/sessions/{sid}/specs", json={"description": "Add CSV export", "kind": "feature"}, headers=H)
    assert r.status_code == 201 and r.json()["name"] == "csv-export" and r.json()["phase"] == "requirements"
    assert client.get(f"/api/sessions/{sid}").json()["session"]["mode"] == "spec"
    listed = client.get(f"/api/sessions/{sid}/specs").json()
    assert listed["active"] == "csv-export" and listed["specs"][0]["doc_paths"]["requirements"].endswith(
        ".codepilot/specs/csv-export/requirements.md")
    assert client.post(f"/api/sessions/{sid}/specs/csv-export/approve", json={"phase": "requirements"},
                       headers=H).status_code == 409  # nothing written yet
    write(repo / ".codepilot/specs/csv-export/requirements.md", "# R")
    ok = client.post(f"/api/sessions/{sid}/specs/csv-export/approve", json={"phase": "requirements"}, headers=H)
    assert ok.json()["phase"] == "design"
    assert client.post(f"/api/sessions/{sid}/specs", json={"name": "csv-export"}, headers=H).status_code == 409
    assert client.post(f"/api/sessions/{sid}/specs/nope/activate", headers=H).status_code == 404


def quick_spec(root, docs=("requirements", "design", "tasks")):
    spec = specs.create(root, "export", profile="quick")
    for doc in docs:
        write(spec.doc(doc), TASKS if doc == "tasks" else f"# {doc}\n")
    return specs.get(root, "export")


def test_a_quick_spec_is_stored_in_the_same_format(repo):
    spec = quick_spec(repo)
    assert spec.profile == "quick" and spec.info(repo)["profile"] == "quick"
    assert json.loads((spec.folder / "spec.json").read_text())["profile"] == "quick"


@pytest.mark.parametrize("state", ['{"kind": "feature", "approved": ""}', '{"profile": "reckless"}', "not json"])
def test_a_spec_without_a_valid_profile_is_full(repo, state):
    write(repo / ".codepilot/specs/old/spec.json", state)
    assert specs.get(repo, "old").profile == "full"


def test_an_unknown_profile_cant_be_created(repo):
    with pytest.raises(ValueError):
        specs.create(repo, "export", profile="reckless")


def test_approving_a_quick_plan_goes_straight_to_implement(repo):
    spec = specs.approve(repo, quick_spec(repo), "tasks")
    assert spec.phase == "implement" and spec.approved == "tasks" and spec.profile == "quick"


def test_a_quick_plan_needs_all_three_documents(repo):
    with pytest.raises(ValueError, match="Write the design and tasks first"):
        specs.approve(repo, quick_spec(repo, ("requirements",)), "tasks")


def test_switching_to_full_keeps_the_documents_and_each_phase_is_approved(repo):
    spec = specs.set_profile(repo, quick_spec(repo), "full")
    assert spec.profile == "full" and spec.phase == "requirements" and spec.doc("tasks").is_file()
    with pytest.raises(ValueError):
        specs.approve(repo, spec, "tasks")
    assert specs.approve(repo, spec, "requirements").phase == "design"


def test_a_quick_spec_past_planning_cant_switch(repo):
    spec = specs.approve(repo, quick_spec(repo), "tasks")
    with pytest.raises(ValueError, match="past planning"):
        specs.set_profile(repo, spec, "full")


def test_a_spec_only_switches_to_full(repo):
    spec = specs.create(repo, "export")
    with pytest.raises(ValueError):
        specs.set_profile(repo, spec, "quick")


def test_a_quick_turn_says_so_and_shows_the_plan_so_far(repo):
    text = specs.turn_text(repo, quick_spec(repo, ("requirements",)))
    assert 'phase="requirements" profile="quick"' in text and "doc='tasks'" in text and "# requirements" in text


def test_a_full_turn_is_unchanged(repo):
    text = specs.turn_text(repo, specs.create(repo, "export"))
    assert "profile=" not in text and "Phase 1 of 3" in text


def test_write_spec_follows_the_profile(cfg, store, repo):
    agent = Agent(cfg, store, llm=FakeLLM([]))
    for name, profile, written in (("quickly", "quick", True), ("fully", "full", False)):
        specs.create(repo, name, profile=profile)
        sess = store.create_session(str(repo), "main")
        store.update_session(sess.id, mode="spec", context_state={"spec": name})
        out, is_error = execute(agent.tools["write_spec"], agent._ctx(store.get_session(sess.id)),
                                {"doc": "tasks", "content": "- [ ] 1. T\n"})
        assert (not is_error) is written and (repo / f".codepilot/specs/{name}/tasks.md").exists() is written


def test_spec_mode_starts_a_quick_spec_of_the_detected_kind(cfg, store, repo):
    for text, name, kind in (("quick add csv export", "csv-export", "feature"),
                             ("quick the export is broken", "export-is-broken", "bugfix")):
        sess = store.create_session(str(repo), "main")
        store.update_session(sess.id, mode="spec")
        list(Agent(cfg, store, llm=FakeLLM([[{"text": "ok"}]])).chat(sess.id, text))
        spec = specs.get(repo, name)
        assert spec.profile == "quick" and spec.kind == kind


def test_the_api_starts_quick_specs_and_switches_them(cfg, store, repo):
    client = TestClient(create_app(cfg, store, Agent(cfg, store, llm=FakeLLM([]))))
    sid = client.post("/api/sessions", json={"repo": str(repo)}, headers=H).json()["id"]
    made = client.post(f"/api/sessions/{sid}/specs", json={"name": "export", "profile": "quick"}, headers=H)
    assert made.status_code == 201 and made.json()["profile"] == "quick"
    bad = client.post(f"/api/sessions/{sid}/specs", json={"name": "other", "profile": "reckless"}, headers=H)
    assert bad.status_code == 400
    url = f"/api/sessions/{sid}/specs/export"
    assert client.post(f"{url}/approve", json={"phase": "tasks"}, headers=H).status_code == 409
    assert client.post(f"{url}/profile", json={"profile": "full"}, headers=H).json()["profile"] == "full"
    write(repo / ".codepilot/specs/quicker/spec.json", '{"profile": "quick", "approved": "tasks"}')
    refused = client.post(f"/api/sessions/{sid}/specs/quicker/profile", json={"profile": "full"}, headers=H)
    assert refused.status_code == 409 and "past planning" in refused.json()["error"]
