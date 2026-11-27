"""Repo hygiene: no mock traces, a calm Dependabot, and vendored files that say what they are and where they came from."""

import json
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


VENDOR = ROOT / "codepilot" / "static" / "vendor"
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
CODEMIRROR = ROOT / "tools" / "codemirror"


def notice_rows():
    """The notices table's rows, as lists of cells (the header and its rule left out)."""
    rows = [line.strip().strip("|").split("|") for line in NOTICES.read_text().splitlines() if line.startswith("|")]
    return [[c.strip() for c in r] for r in rows[2:]]


def test_every_vendored_script_is_in_the_notices_with_its_licence_text():
    """A vendored file ships to every user under its own licence: the notices name each one, and its licence text."""
    rows = notice_rows()
    named = {f for r in rows for f in re.findall(r"`([^`]+\.js)`", r[1])}
    scripts = {p.name for p in VENDOR.glob("*.js")}
    assert scripts <= named, f"vendored but not in THIRD_PARTY_NOTICES.md: {sorted(scripts - named)}"
    for r in rows:
        for licence in re.findall(r"`codepilot/static/vendor/([^`]+)`", r[-1]):
            assert (VENDOR / licence).is_file(), f"{r[0]}: {licence} is named but missing"


def test_the_codemirror_recipe_pins_exact_versions_and_the_bundle_was_built_from_them():
    """No ranges: the same recipe builds the same file. And a version bumped in package.json without a rebuild shows
    up here, because the bundle's first line names the versions it was built from."""
    deps = json.loads((CODEMIRROR / "package.json").read_text())["devDependencies"]
    loose = {name: v for name, v in deps.items() if not re.fullmatch(r"\d+\.\d+\.\d+", v)}
    assert not loose, f"tools/codemirror/package.json must pin exact versions: {loose}"
    banner = (VENDOR / "codemirror.min.js").open().readline()
    stale = [f"{name} {v}" for name, v in deps.items() if name != "esbuild" and f"{name} {v}" not in banner]
    assert not stale, f"codemirror.min.js wasn't rebuilt for: {stale} (sh tools/codemirror/build.sh)"
    row = next((r for r in notice_rows() if "codemirror.min.js" in r[1]), None)
    assert row and deps["@codemirror/view"] in row[2], "THIRD_PARTY_NOTICES.md: CodeMirror's row names its version"


def test_the_apps_own_scripts_import_nothing_from_a_package_manager():
    """Classic scripts, no build step: only a file in static/vendor/ may come from npm (5.3). An import or require in
    one of the app's own scripts would need a bundler to run."""
    pattern = re.compile(r"^\s*import\s[^(]|^\s*export\s|\brequire\(\s*['\"]|\bimport\(\s*['\"](?!/static/)", re.M)
    hits = [p.name for p in (ROOT / "codepilot" / "static").glob("*.js") if pattern.search(p.read_text())]
    assert not hits, f"these load from a package manager, which needs a build step: {hits}"
