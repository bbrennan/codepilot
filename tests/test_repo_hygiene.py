"""The repo ships no mock traces: nothing under examples/ looks like an agent run, and the docs don't point at one."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACE_DIRS = {"traces", "trace", "journeys", "eval_results"}


def test_examples_contain_no_mock_traces():
    found = [p for p in (ROOT / "examples").rglob("*") if p.name in TRACE_DIRS or p.name == "run_journeys.py"]
    assert not found, f"mock traces still in the repo: {found}"


def test_docs_do_not_advertise_sample_traces():
    for doc in [ROOT / "README.md", *(ROOT / "docs").glob("*.md"), *(ROOT / "examples").rglob("*.md")]:
        text = doc.read_text().lower()
        assert "sample traces" not in text and "traces.webp" not in text, doc
