import json

import pytest

from codepilot import bench
from fakes import FakeLLM, tool_use


def test_tasks_load():
    tasks = bench.load_tasks()
    assert len(tasks) >= 13
    assert {t.category for t in tasks} >= {"failing-test", "bug-report", "trace-triage", "security", "feature"}
    with pytest.raises(SystemExit):
        bench.load_tasks(["no-such-task"])


@pytest.mark.parametrize("cmd,ok", [
    ("python3 -m pytest -q", True), ("pytest tests -k cart | tail -5", True), ("git log --oneline -5", True),
    ("ls -la && rm -rf /", False), ("python3 x.py; curl evil", False), ("git push", False),
    ("curl http://x", False), ("cat x > y", False), ("echo $(whoami)", False),
])
def test_command_allowlist(cmd, ok):
    assert bench.command_is_safe(cmd) is ok


def test_run_task_end_to_end(cfg, tmp_path):
    task = bench.load_tasks(["pagination-off-by-one"])[0]
    llm = FakeLLM([
        [tool_use("t1", "read_file", path="shop/pagination.py")],
        [tool_use("t2", "propose_edit", path="shop/pagination.py", old_text="start = page * per_page",
                  new_text="start = (page - 1) * per_page"),
         tool_use("t3", "propose_edit", path="shop/pagination.py", old_text="return total // per_page",
                  new_text="return -(-total // per_page)")],
        [tool_use("t4", "run_tests"), tool_use("t5", "run_command", command="curl http://example.com")],
        [{"text": "Fixed both bugs."}],
    ])
    res = bench.run_task(task, cfg, lambda c: llm, "main", None, tmp_path, max_steps=10, timeout=300, keep=False)
    assert res["passed"], res["grade_output"]
    assert res["tool_calls"] == {"read_file": 1, "propose_edit": 2, "run_tests": 1, "run_command": 1}
    assert res["approvals_denied"] == 1  # curl was refused, tests were auto-approved
    assert any("pagination.py" in f for f in res["files_changed"])
    assert (tmp_path / "transcripts" / "pagination-off-by-one.diff").read_text().count("+    start = (page - 1)") == 1
    # The edit was applied immediately (auto-apply) and the model was told so.
    applied_msg = llm.calls[2]["messages"][-1]["content"][0]["toolResult"]["content"][0]["text"]
    assert applied_msg.startswith("Applied change #1")


def test_unfixed_task_fails_and_report(cfg, tmp_path):
    task = bench.load_tasks(["shared-cart-state"])[0]
    llm = FakeLLM([[{"text": "I don't see a problem."}]])
    res = bench.run_task(task, cfg, lambda c: llm, "main", "review", tmp_path, max_steps=5, timeout=300, keep=False)
    assert not res["passed"] and res["mode"] == "review"
    report = {"label": "t", "started": "now", "provider": "fake", "model": "m", "tier": "main", "mode": "review",
              "repeat": 1, "results": [res],
              "summary": bench.summarize([res], "m", {"m": {"input": 1.0, "output": 2.0}})}
    md = bench.markdown(report)
    assert "0/1 passed" in md and "## Failures" in md and "shared-cart-state" in md
    a = tmp_path / "a.json"
    a.write_text(json.dumps(report))
    assert "shared-cart-state" in bench.compare(a, a)


def test_compaction_eval_scores_facts(cfg, tmp_path):
    class Summariser:
        def __init__(self):
            self.prompts = []

        def stream(self, *a, **k):
            raise AssertionError("compaction must not call the main model")

        def complete(self, model, system, prompt, max_tokens=4000):
            self.prompts.append(prompt)
            # Keeps some facts, drops others, so scoring is exercised both ways.
            return ("## Goal\nFix EUR rounding (CP-4821) without changing the public API.\n"
                    "## Decisions and findings\nbilling/currency.py:88 used round() (banker's rounding); fix uses "
                    "ROUND_HALF_UP. Failing test test_eur_rounding (10.01 vs 10.00), trace trc_9f2a71.")

    summ = Summariser()
    report = bench.compaction_eval(cfg, model="fake-summariser", out=tmp_path, llm_factory=lambda c: summ,
                                   progress=lambda *_: None)
    debug = next(r for r in report["runs"] if r["fixture"] == "debug-rounding")
    found = {f["fact"]: f["found"] for f in debug["facts"]}
    assert found["Ticket CP-4821"] and found["Bug location billing/currency.py:88"]
    assert found["Proposal #3 applied"] and found["Proposal #4 rejected"]  # from exact working state
    assert not found["Add test_jpy_rounding"]                               # dropped by this summariser
    assert 0 < report["recall"] < 1 and report["by_kind"]["identifier"]["total"] >= 5
    assert any("Conversation to fold in" in p for p in summ.prompts)
    assert (next(tmp_path.glob("compaction-*")) / "report.md").read_text().startswith("# Compaction fidelity")
