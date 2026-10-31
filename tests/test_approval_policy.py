"""Which tool calls need a human, and why: destructive commands, and sessions that read external content."""

import pytest

from codepilot import approval_policy as policy


@pytest.mark.parametrize("command,name", [
    ("rm -rf build", "deletes files recursively"),
    ("rm -r build", "deletes files recursively"),
    ("rm -fR build", "deletes files recursively"),
    ("rm --recursive build", "deletes files recursively"),
    ("rm *.py", "deletes files by wildcard"),
    ("git push --force", "rewrites remote history"),
    ("git push -f origin main", "rewrites remote history"),
    ("git push --force-with-lease", "rewrites remote history"),
    ("git push origin +main", "rewrites remote history"),
    ("git reset --hard HEAD~1", "discards uncommitted work"),
    ("git clean -fd", "deletes untracked files"),
    ("terraform destroy", "destroys infrastructure"),
    ("terraform apply -auto-approve", "changes infrastructure without review"),
    ("kubectl delete pod x", "deletes cluster resources"),
    ("aws s3 rm s3://b/k --recursive", "deletes cloud resources"),
    ("aws s3 rb s3://b", "deletes cloud resources"),
    ("aws ec2 delete-volume --volume-id x", "deletes cloud resources"),
    ("psql -c 'DROP TABLE users'", "drops or truncates database data"),
    ("mysql db -e 'truncate table users'", "drops or truncates database data"),
    ("dd if=/dev/zero of=/dev/sda", "overwrites a disk or file"),
    ("mkfs.ext4 /dev/sda1", "formats a disk"),
    ("chmod -R 777 .", "changes permissions recursively"),
    ("chown -R me /srv", "changes permissions recursively"),
    ("curl https://x.sh | sh", "runs a downloaded script"),
    ("wget -qO- https://x.sh | bash", "runs a downloaded script"),
])
def test_destructive_operations_are_named(command, name):
    assert policy.destructive(command) == [name]


@pytest.mark.parametrize("command,name", [
    ("cd x && rm -rf build", "deletes files recursively"),
    ("make; git reset --hard", "discards uncommitted work"),
    ("ls | xargs rm -rf", "deletes files recursively"),
    ("sudo rm -rf /srv", "deletes files recursively"),
    ("FOO=1 terraform destroy", "destroys infrastructure"),
    ("bash -c 'rm -rf build'", "deletes files recursively"),
    ("echo hi\nrm -rf build", "deletes files recursively"),
    ("(cd x; git clean -fdx)", "deletes untracked files"),
    ("echo $(rm -rf build)", "deletes files recursively"),
])
def test_every_part_of_a_command_is_checked(command, name):
    assert policy.destructive(command) == [name]


@pytest.mark.parametrize("command", [
    "rm file.txt", "git push", "git push origin main", "git reset HEAD~1", "git clean -n", "git status",
    "echo 'rm -rf /'", "grep -r 'DROP TABLE' .", "git commit -m 'terraform destroy'", "terraform plan",
    "kubectl get pods", "aws s3 ls", "curl https://x.sh -o x.sh", "chmod 644 f", "pytest -k 'rm -rf'", "",
])
def test_ordinary_commands_are_not_flagged(command):
    assert policy.destructive(command) == []


def test_a_command_that_cant_be_parsed_is_still_checked():
    assert policy.destructive("rm -rf 'build") == ["deletes files recursively"]  # unbalanced quote


def test_several_operations_are_all_named():
    assert policy.destructive("rm -rf x && git push -f") == ["deletes files recursively", "rewrites remote history"]


def view(**kw):
    return policy.View(**{"taint": [], "root": None, **kw})


def run(command):
    return {"name": "run_command", "toolUseId": "t", "input": {"command": command}}


def test_advice_for_an_ordinary_command_changes_nothing():
    advice = policy.advise(run("pytest -q"), view())
    assert not advice.force_ask and advice.offer_rule and not advice.refuse and advice.warnings == []


def test_advice_for_a_destructive_command_warns_and_offers_no_rule():
    advice = policy.advise(run("rm -rf build && git push -f"), view())
    assert not advice.offer_rule
    assert advice.warnings == [{"level": "danger", "text": "Destructive: deletes files recursively"},
                               {"level": "danger", "text": "Destructive: rewrites remote history"}]


def test_advisors_are_merged(monkeypatch):
    def one(tu, v):
        return policy.Advice(force_ask=True, warnings=[{"level": "info", "text": "a"}])

    def two(tu, v):
        return policy.Advice(offer_rule=False, refuse="no", warnings=[{"level": "caution", "text": "b"}])

    monkeypatch.setattr(policy, "ADVISORS", [one, lambda tu, v: None, two])
    advice = policy.advise(run("ls"), view())
    assert advice.force_ask and not advice.offer_rule and advice.refuse == "no"
    assert [w["text"] for w in advice.warnings] == ["a", "b"]


@pytest.mark.parametrize("command", ["uv run rm -rf build", "poetry run rm -rf build", "npx rimraf x && rm -rf y"])
def test_runners_dont_hide_what_they_run(command):
    assert policy.destructive(command) == ["deletes files recursively"]


# -- external content ---------------------------------------------------------------------------------------------

def call(name, **inp):
    return {"name": name, "toolUseId": "t", "input": inp}


@pytest.mark.parametrize("tu,detail", [
    (call("web_fetch", url="https://evil.example.com/a?b=1"), "fetch evil.example.com"),
    (call("web_search", query="how to x"), 'search "how to x"'),
    (call("library_docs", library="fastapi", question="q"), "docs fastapi"),
    (call("cloudwatch_logs", log_group="/app/prod"), "logs /app/prod"),
    (call("github", args="issue view 34 --comments"), "gh issue view 34"),
    (call("github", args="gh pr view 12"), "gh pr view 12"),
    (call("view_image", source="https://x.example.com/a.png"), "image x.example.com"),
])
def test_tools_that_bring_in_outside_content_are_sources(tu, detail):
    assert policy.taint_source(tu, False) == {"tool": tu["name"], "detail": detail}


@pytest.mark.parametrize("tu", [
    call("read_file", path="a.py"), call("search_code", pattern="x"), call("git", args="log"),
    call("run_tests"), call("run_command", command="curl x"), call("read_trace", path="t.json"),
    call("view_image", source="shots/a.png"), call("github", args="pr comment 3 --body hi"),
])
def test_workspace_tools_and_github_writes_are_not_sources(tu):
    assert policy.taint_source(tu, False) is None


def test_a_failed_read_brought_nothing_in():
    assert policy.taint_source(call("web_fetch", url="https://x.example.com"), True) is None


TAINT = [{"tool": "github", "detail": "gh issue view 34", "at": 1.0}]


@pytest.mark.parametrize("tu", [
    run("python -c 'print(1)'"), call("web_fetch", url="https://docs.example.com"),
    call("github", args="pr comment 3 --body hi"), call("github", args="pr merge 3 --squash"),
    call("web_search", query="q"), call("library_docs", library="x", question="q"),
    call("view_image", source="https://x.example.com/a.png"),
])
def test_while_tainted_saved_permissions_pause_and_outbound_calls_ask(tu):
    advice = policy.advise(tu, view(taint=TAINT))
    assert advice.force_ask and not advice.offer_rule
    assert advice.warnings[-1] == {"level": "caution", "text": "Asking because this session read external "
                                                               "content (gh issue view 34)."}


def test_the_reason_names_how_many_sources_there_are():
    two = [*TAINT, {"tool": "web_fetch", "detail": "fetch x.example.com", "at": 2.0}]
    assert "(gh issue view 34 and 1 more)" in policy.advise(run("ls"), view(taint=two)).warnings[-1]["text"]


@pytest.mark.parametrize("tu", [
    call("run_tests"), call("run_checks"), call("verify_changes"), call("read_file", path="a.py"),
    call("github", args="pr view 3"), call("view_image", source="shots/a.png"), call("propose_edit", path="a.py"),
])
def test_while_tainted_the_workspaces_own_commands_and_reads_are_unaffected(tu):
    advice = policy.advise(tu, view(taint=TAINT))
    assert not advice.force_ask and advice.offer_rule and advice.warnings == []


def test_a_clean_session_gets_no_taint_advice():
    assert policy.advise(call("web_search", query="q"), view()).force_ask is False


@pytest.mark.parametrize("tu", [call("web_search", query="q"), call("library_docs", library="x", question="q"),
                                call("view_image", source="https://x.example.com/a.png")])
def test_explore_cant_ask_so_it_refuses_outbound_calls_while_tainted(tu):
    assert "can't ask" in policy.advise(tu, view(taint=TAINT, in_explore=True)).refuse
