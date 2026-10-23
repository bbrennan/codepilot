"""Spec-driven development: spec files, phases and approvals, the agent's spec tools, and the endpoints."""

import pytest
from fakes import FakeLLM, tool_use
from starlette.testclient import TestClient

from codepilot import specs
from codepilot.agent import Agent
from codepilot.server import create_app

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


def test_discover_codepilot_kiro_and_spec_kit(repo):
    created = specs.create(repo, "csv-export")
    write(repo / ".kiro/specs/auth-flow/requirements.md", "# Req")
    write(repo / ".kiro/specs/auth-flow/design.md", "# Design")
    write(repo / "specs/001-search/spec.md", "# Spec")
    write(repo / "specs/001-search/plan.md", "# Plan")
    write(repo / "specs/001-search/tasks.md", "- [ ] 1. Index")
    found = {s.name: s for s in specs.discover(repo)}
    assert found["csv-export"].source == "codepilot" and found["csv-export"].phase == "requirements"
    assert found["auth-flow"].source == "kiro" and found["auth-flow"].phase == "tasks"  # inferred from files
    assert found["001-search"].source == "speckit" and found["001-search"].phase == "implement"
    assert found["001-search"].doc("design").name == "plan.md" and len(found["001-search"].tasks) == 1
    assert created.doc("requirements").name == "requirements.md"
    assert specs.create(repo, "bad-login", "bugfix").doc("requirements").name == "bugfix.md"


def test_approvals_go_in_order_and_never_backwards(repo):
    spec = specs.create(repo, "csv-export")
    with pytest.raises(FileNotFoundError):
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
