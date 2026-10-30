"""The repo ships no mock traces: nothing under examples/ looks like an agent run, and the docs don't point at one."""

import re
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


def test_dependabot_is_grouped_limited_and_slow():
    """An unconfigured Dependabot opened seven PRs at once. It must group updates, keep one PR open per ecosystem, run
    monthly, and leave major-version jumps (e.g. actions/checkout 4 -> 7) to a person."""
    text = (ROOT / ".github" / "dependabot.yml").read_text()
    ecosystems = text.count("package-ecosystem:")
    assert ecosystems == 2
    assert text.count("interval: monthly") == ecosystems
    assert text.count("groups:") == ecosystems
    assert text.count("version-update:semver-major") == ecosystems
    limits = [int(x) for x in re.findall(r"open-pull-requests-limit:\s*(\d+)", text)]
    assert limits == [1] * ecosystems, limits  # exactly one open PR per ecosystem; raising it must fail this
    assert "target-branch: develop" in text


def test_dependabot_updates_the_lockfile_not_our_declared_version_ranges():
    """Raising `anthropic>=2.1` to `>=2.3` just because 2.3 exists forces every user to upgrade for nothing. The
    declared ranges are a compatibility promise; Dependabot may only move what is locked."""
    text = (ROOT / ".github" / "dependabot.yml").read_text()
    uv_block = text.split("package-ecosystem: uv", 1)[1].split("package-ecosystem:", 1)[0]
    assert "versioning-strategy: lockfile-only" in uv_block
