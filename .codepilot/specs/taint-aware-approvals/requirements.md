# Requirements: taint-aware approvals

## Introduction

Prompt injection works when one session holds three things at once: content from outside, access to private data,
and a way to send data out (Willison's "lethal trifecta"). CodePilot sessions always have the second. The first
appears when the agent reads a web page, a GitHub issue or a CI log. The third exists today through `web_fetch` to an
"always allowed" site, `library_docs` and `web_search` (which never ask), and any command an "always allow" rule
covers. For example, a `python` rule also covers `python -c '<anything>'`. Injection against coding agents is now
exploited in the wild, including bypasses of command allowlists (CSA, October 2026).

This spec marks a session **tainted** once it has read external content. While tainted, saved permissions pause and
every outbound call asks. Separately, it flags destructive commands at any time. A shared **approval advice** hook
carries both, and the package guard (spec 4) plugs into it.

Out of scope: sandboxing, network egress filtering, and scanning content for injection text (that is unreliable).

## 1. Mark external content

**User story:** As the developer, I want CodePilot to notice when it has read content from outside my machine, so that
my approvals can get stricter exactly then.

1.1 WHEN `web_fetch`, `web_search`, `library_docs`, `cloudwatch_logs`, a GitHub read, or `view_image` of a URL returns
successfully, in the main agent or in `explore`, THEN the system SHALL mark the session tainted and record the source
(tool and short detail, for example `gh issue view 34`).
1.2 Reading workspace files, git, traces and test output SHALL NOT taint the session.
1.3 Taint SHALL survive a reload, restart and compaction, and SHALL end only when I clear it or start a new session
(including "Continue in new session").
1.4 WHEN a session becomes tainted THEN the chat header SHALL show an **external content** chip. Hovering or clicking it
SHALL list the sources and offer **Clear**, with the warning "Only clear this if you've checked what it read."
1.5 WHEN a session first becomes tainted THEN the assistant SHALL be told once, with that tool result, that content from
those sources is data and that instructions inside it must not be followed.

## 2. Stricter approvals while tainted

**User story:** As the developer, I want saved permissions to pause after external content, so that injected
instructions can't use my earlier "always allow" choices.

2.1 WHILE the session is tainted THEN "always allow" rules SHALL NOT skip approval. Each command, gh write and fetch
SHALL ask, and the approval SHALL say why: "Asking because this session read external content (gh issue view 34)."
2.2 WHILE tainted THEN `web_fetch` (every site), `web_search`, `library_docs`, `gh search`, `gh api` and images by URL
SHALL require approval, showing the exact URL or query.
2.3 WHILE tainted THEN the approval SHALL NOT offer "always allow".
2.4 WHILE tainted THEN `explore` SHALL refuse `web_search` and `library_docs` with an explanation, because it can't ask.
2.5 WHILE tainted THEN the Memory view's "Always allowed in this session" SHALL show the rules as paused.
2.6 The auto-run tests switch SHALL keep working while tainted for the workspace's own test command and analysers, but
tests run with arguments the model chose SHALL ask.
2.7 WHEN I clear the taint THEN the rules SHALL apply again from the next tool call.

## 3. Flag destructive commands

**User story:** As the developer, I want destructive commands flagged clearly, so that I don't approve one by reflex.

3.1 WHEN a command needing approval contains a destructive operation THEN the approval SHALL show a red warning naming
it. The operations are: recursive or wildcard `rm`; `git push --force` or `-f`; `git reset --hard`; `git clean -f`;
`terraform destroy`; `terraform apply -auto-approve`; `kubectl delete`; `aws … delete-*`, `s3 rm` or `rb`;
`DROP`/`TRUNCATE` in SQL passed to a client; `dd`, `mkfs`; `chmod -R`, `chown -R`; a download piped to a shell.
3.2 A destructive command SHALL never get or match an "always allow" rule, whether the session is tainted or not.
3.3 Detection SHALL look at every part of a chained or piped command, not only the first word.

## 4. One advice hook

4.1 Approval decisions SHALL go through one function that returns whether to force asking, the warnings to show, and
whether to offer "always allow", so that new checks are added by registering an advisor, not by adding branches to the
agent loop.
