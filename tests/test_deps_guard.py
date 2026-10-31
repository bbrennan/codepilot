"""Package guard: what a command or manifest edit would install, and what the public registries say about it."""

import http.client
import json
from datetime import datetime, timezone

import pytest

from codepilot import deps_guard as dg

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc).timestamp()
DAY = 86400


@pytest.mark.parametrize("command,pairs", [
    ("pip install requests", [("pypi", "requests")]),
    ("pip3 install requests flask", [("pypi", "requests"), ("pypi", "flask")]),
    ("python -m pip install 'requests[socks]>=2'", [("pypi", "requests")]),
    ("python3 -m pip install -U requests==2.0", [("pypi", "requests")]),
    ("uv add fastapi", [("pypi", "fastapi")]),
    ("uv add --dev pytest", [("pypi", "pytest")]),
    ("uv add --group test pytest", [("pypi", "pytest")]),
    ("uv pip install numpy", [("pypi", "numpy")]),
    ("poetry add django", [("pypi", "django")]),
    ("pipx install ruff", [("pypi", "ruff")]),
    ("npm install left-pad", [("npm", "left-pad")]),
    ("npm i -D typescript@5", [("npm", "typescript")]),
    ("npm add @scope/pkg@1.2.3", [("npm", "@scope/pkg")]),
    ("pnpm add vite", [("npm", "vite")]),
    ("yarn add react", [("npm", "react")]),
    ("bun add zod", [("npm", "zod")]),
    ("cargo add serde", [("crates", "serde")]),
    ("cargo add serde@1 --features derive", [("crates", "serde")]),
    ("cd x && uv add foo", [("pypi", "foo")]),
    ("sudo pip install foo", [("pypi", "foo")]),
    ("uv run pip install foo", [("pypi", "foo")]),
    ("npm install react@npm:reqeusts@1", [("npm", "reqeusts")]),
    ("npm i alias@npm:@scope/real@2", [("npm", "@scope/real")]),
    ("pip --isolated install reqeusts", [("pypi", "reqeusts")]),
    ("python -m pip --isolated install reqeusts", [("pypi", "reqeusts")]),
    ("pip --python /usr/bin/python3 install foo", [("pypi", "foo")]),
    ("uv --directory sub add foo", [("pypi", "foo")]),
    ("npm --prefix web install foo", [("npm", "foo")]),
    ("cargo add --optional reqeusts", [("crates", "reqeusts")]),
    ("npm install --optional foo", [("npm", "foo")]),
    ("npm i -f foo", [("npm", "foo")]),
    ("pnpm add -r foo", [("npm", "foo")]),
    ("uv add --optional extra foo", [("pypi", "foo")]),
    ("cargo add -p member foo", [("crates", "foo")]),
    ("npm i --registry https://r.example.com foo", [("npm", "foo")]),
])
def test_installs_finds_what_a_command_would_install(command, pairs):
    assert dg.installs(command) == pairs


@pytest.mark.parametrize("command", [
    "pip install -r requirements.txt", "pip install -e .", "pip install .", "pip install ./pkg",
    "pip install https://x.example.com/a.whl", "pip install git+https://github.com/a/b",
    "npm install", "npm ci", "uv sync", "uv pip list", "cargo build", "pip uninstall foo", "pip show foo",
    "echo pip install foo", "npm install ./local", "cargo add --path ../x", "pip install -i https://x/simple",
])
def test_installs_ignores_what_isnt_a_registry_name(command):
    assert dg.installs(command) == []


def test_a_package_named_twice_is_checked_once():
    assert dg.installs("pip install foo && uv add foo") == [("pypi", "foo")]


@pytest.mark.parametrize("path,before,after,pairs", [
    ("pyproject.toml", '[project]\ndependencies = ["a>=1"]\n', '[project]\ndependencies = ["a>=2", "b[x]>=1"]\n',
     [("pypi", "b")]),
    ("sub/pyproject.toml", "", '[project.optional-dependencies]\nt = ["c"]\n[dependency-groups]\ndev = ["d"]\n',
     [("pypi", "c"), ("pypi", "d")]),
    ("pyproject.toml", "", '[tool.poetry.dependencies]\npython = "^3.11"\ne = "*"\n'
                           '[tool.poetry.group.dev.dependencies]\nf = "*"\n', [("pypi", "e"), ("pypi", "f")]),
    ("requirements.txt", "a==1\n", "a==2\n# c\nb>=1 ; python_version > '3'\n-r other.txt\n-e .\n", [("pypi", "b")]),
    ("requirements-dev.txt", "", "c\n", [("pypi", "c")]),
    ("package.json", '{"dependencies": {"a": "1"}}',
     '{"dependencies": {"a": "2", "b": "1"}, "devDependencies": {"c": "1", "@s/d": "1", "e": "file:../e"}}',
     [("npm", "b"), ("npm", "c"), ("npm", "@s/d")]),
    ("Cargo.toml", '[dependencies]\na = "1"\n',
     '[dependencies]\na = "2"\nb = "1"\nl = { path = "../l" }\n[dev-dependencies]\nc = { version = "1" }\n',
     [("crates", "b"), ("crates", "c")]),
    ("package.json", '', '{"dependencies": {"react": "npm:reqeusts@1", "x": "npm:@s/real@2"}}',
     [("npm", "reqeusts"), ("npm", "@s/real")]),
    ("package.json", '{"dependencies": {"react": "npm:good@1"}}', '{"dependencies": {"react": "npm:bad@1"}}',
     [("npm", "bad")]),  # the same key, a different package
    ("package.json", '', '{"dependencies": {"g": "user/repo", "h": "github:a/b", "i": "^1.0"}}', [("npm", "i")]),
    ("pyproject.toml", "", '[project]\ndependencies = ["x @ git+https://github.com/a/b", "y"]\n', [("pypi", "y")]),
])
def test_added_finds_new_dependencies_in_a_manifest_edit(path, before, after, pairs):
    assert dg.added(path, before, after) == pairs


@pytest.mark.parametrize("path,before,after", [
    ("pyproject.toml", '[project]\ndependencies = ["a"]\n', '[project]\ndependencies = [\n  "a",\n]\n'),  # a reformat
    ("pyproject.toml", "", "not [valid toml"),
    ("package.json", "", "{not json"),
    ("notes.txt", "", "requests\n"),
    ("src/app.py", "", "import requests\n"),
])
def test_edits_that_add_no_dependency(path, before, after):
    assert dg.added(path, before, after) == []


def pypi(*uploads):
    return json.dumps({"releases": {str(i): [{"upload_time_iso_8601": u}] for i, u in enumerate(uploads)}})


def fake_http(responses):
    calls = []

    def get(url, timeout):
        calls.append(url)
        answer = responses[url]
        if isinstance(answer, Exception):
            raise answer
        return answer
    get.calls = calls
    return get


def test_lookup_reads_each_registry(monkeypatch):
    http = fake_http({
        "https://pypi.org/pypi/old-pkg/json": pypi("2014-01-01T00:00:00Z", "2020-01-01T00:00:00Z"),
        "https://registry.npmjs.org/%40s%2Fp": json.dumps({"time": {"created": "2015-06-01T00:00:00.000Z"},
                                                           "versions": {"1": {}, "2": {}, "3": {}}}),
        "https://crates.io/api/v1/crates/serde": json.dumps({"crate": {"created_at": "2016-01-01T00:00:00+00:00"},
                                                             "versions": [{}, {}]}),
    })
    py = dg.lookup("pypi", "Old_Pkg", http=http, now=NOW)  # PEP 503 name
    assert py.found and py.releases == 2 and datetime.fromtimestamp(py.created, timezone.utc).year == 2014
    js = dg.lookup("npm", "@s/p", http=http, now=NOW)
    assert js.found and js.releases == 3
    rs = dg.lookup("crates", "serde", http=http, now=NOW)
    assert rs.found and rs.releases == 2


def test_lookup_tells_missing_from_unreachable():
    http = fake_http({"https://pypi.org/pypi/nope/json": dg.NotFound(), "https://pypi.org/pypi/down/json": OSError("x"),
                      "https://pypi.org/pypi/garbled/json": "<html>"})
    assert dg.lookup("pypi", "nope", http=http, now=NOW).found is False
    assert dg.lookup("pypi", "down", http=http, now=NOW).found is None
    assert dg.lookup("pypi", "garbled", http=http, now=NOW).found is None


@pytest.mark.parametrize("failure", [http.client.IncompleteRead(b"{"), '{"releases": null}', "[]", '"text"',
                                     '{"crate": 3}', '{"time": null}'])
def test_a_broken_response_is_unknown_never_an_error(failure):
    for eco, url in (("pypi", "https://pypi.org/pypi/x/json"), ("npm", "https://registry.npmjs.org/x"),
                     ("crates", "https://crates.io/api/v1/crates/x")):
        dg.CACHE.clear()
        assert dg.lookup(eco, "x", http=fake_http({url: failure}), now=NOW).found is None


def test_results_are_cached_for_an_hour_and_failures_briefly():
    http = fake_http({"https://pypi.org/pypi/a/json": pypi("2014-01-01T00:00:00Z"),
                      "https://pypi.org/pypi/b/json": OSError("x")})
    for when in (NOW, NOW + 3000):
        dg.lookup("pypi", "a", http=http, now=when)
    assert len(http.calls) == 1
    dg.lookup("pypi", "a", http=http, now=NOW + 3700)
    assert len(http.calls) == 2
    for when in (NOW, NOW + 10):
        dg.lookup("pypi", "b", http=http, now=when)
    dg.lookup("pypi", "b", http=http, now=NOW + 120)
    assert http.calls.count("https://pypi.org/pypi/b/json") == 2


@pytest.mark.parametrize("info,level,fragment", [
    (dg.Info("pypi", "x", False, None, None), "danger", "not on PyPI"),
    (dg.Info("npm", "x", False, None, None), "danger", "not on npm"),
    (dg.Info("pypi", "x", None, None, None), "info", "couldn't reach PyPI"),
    (dg.Info("pypi", "x", True, NOW - 89 * DAY, 10), "caution", "first published 89 days ago"),
    (dg.Info("pypi", "x", True, NOW - 91 * DAY, 3), "info", "on PyPI since 2026"),
    (dg.Info("pypi", "x", True, NOW - 900 * DAY, 2), "caution", "2 releases"),
    (dg.Info("crates", "x", True, NOW - 900 * DAY, 213), "info", "213 releases"),
])
def test_verdict_grades_a_package(info, level, fragment):
    got_level, text = dg.verdict(info, NOW)
    assert got_level == level and fragment in text


def test_check_reports_each_package_and_caps_the_list():
    http = fake_http({f"https://pypi.org/pypi/p{i}/json": dg.NotFound() for i in range(25)})
    pairs = [("pypi", f"p{i}") for i in range(25)]
    lines = dg.check(pairs, http=http, now=NOW)
    assert len(lines) == 21 and lines[0]["name"] == "p0" and lines[0]["level"] == "danger"
    assert lines[-1]["level"] == "info" and "5 more not checked" in lines[-1]["text"]
