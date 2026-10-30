# Design: verification receipts

## Overview

Verifying takes six steps. Each is a small function, so tests can inject a fake copier and runner.
1. Clone the workspace into a scratch folder.
2. Apply the pending proposals to the clone.
3. Run the test command and the analysers on the changed files.
4. On failure, revert the clone to its original state and run again to get a baseline.
5. Store a receipt.
6. Stream it as an event.

There are two entry points. The agent's `verify_changes` tool runs during a turn (requirement 3). The automatic run or
the **Verify** button runs at the end of a turn (requirement 1). Both go through `verification.verify()`.

## Architecture

```
end of turn (Agent._loop_steps)  ─┐
POST /api/sessions/{sid}/verify  ─┼─► Agent.verify(sid) ──► verification.verify(root, cfg, proposals, …) ─► Receipt
verify_changes tool (tools.py)   ─┘                                   │
                                                                      └─► store.add_receipt / latest_receipt
browser ◄── {"type":"verification", "receipt": {...}} ── NDJSON turn stream (reload/follow work as today)
```

### New: `codepilot/verification.py`

Its one reason to change is how pending changes are checked before review.

```python
@dataclass
class Run:            # one command on the copy
    name: str         # "tests" or an analyser name
    kind: str         # tests | lint | types | security
    argv: str
    exit: int | None  # None = timed out
    output: str       # tail, 6000 chars
    baseline_exit: int | None = None   # set only when exit != 0 (1.5)

@dataclass
class Receipt:
    proposal_ids: list[int]
    fingerprint: str  # sha1 over (id, path, old_text, new_text) of every pending proposal, in id order
    status: str       # pass | fail | preexisting (failures that also happen without the changes) | unverified (passed,
                      # but isolation is in doubt: 1.8) | nothing | error | timeout | cancelled
    runs: list[Run]
    newly_failing: list[str]   # test ids or analyser findings present only with the changes
    conflict: str = ""         # 1.6
    isolation: list[str] = []  # 1.8: copied files that may still run the workspace's code ([] = fully separated)
    seconds: float = 0.0

def fingerprint(proposals) -> str
def verify(root: Path, cfg: Config, proposals: list[Proposal], *, workdir: Path, copier=clone_tree,
           runner=run_argv, cancelled=lambda: False, timeout=600, analysers=True, clock=time.monotonic) -> Receipt
def prepared(root, proposals, workdir, copier) -> ContextManager[Copy]   # clone, re-point, apply; always removed
def verify_session(store, cfg, sid, root, cancelled) -> dict | None      # verify the pending set and store the receipt
def describe(receipt: dict, lead="") -> str                              # the receipt as text for the model
def clone_tree(src: Path, dst: Path) -> None
def relocate_envs(src: Path, dst: Path) -> list[str]   # rewrites copied virtualenvs; returns files still naming src
def newly_failing(name: str, after: str, after_exit: int, before: str, before_exit: int) -> list[str]
```

- **`clone_tree`** copies the whole folder, including `.git` and any virtualenv, with copy-on-write where the
  filesystem supports it. On macOS APFS that is `cp -c -R` (clonefile: this repo, 265 MB, took 4.8 s). On Linux it is
  `cp -a --reflink=auto`. Otherwise it is `shutil.copytree(..., symlinks=True)`. Nothing is symlinked back to the
  workspace, because a shared virtualenv would run the workspace's code (next point). The workspace itself is only
  ever read (1.4).
- **`relocate_envs` (1.8), found by experiment on this repo.** A copied virtualenv still runs the *original* code:
  - its `bin/` scripts (`pytest`, …) start with `#!<workspace>/.venv/bin/python`;
  - editable installs (`__editable__*_finder.py`, `*.pth`, `direct_url.json`) map the package to `<workspace>/…`.
  So `uv run pytest` in a plain copy imported `<workspace>/codepilot/checkpoints.py`, and a deliberately broken test
  passed. Rewriting `<workspace>` to `<copy>` in those files fixed it: the copy imported its own code and the broken
  test failed.
  - For every folder in the copy that has a `pyvenv.cfg` (at most two levels deep: `.venv`, `venv`, `env`, `.tox/*`),
    rewrite the workspace path to the copy's path in the regular, non-binary files of `bin/` (or `Scripts/`) and in the
    top-level `*.pth`, `*.py` and `*.dist-info/direct_url.json` files of `site-packages`.
  - Then scan those same files again. Any that still name the workspace go into `Receipt.isolation`, and the receipt
    can't show a plain pass (1.8).
  - Node needs none of this: `node_modules/.bin` links are relative, and Go and Cargo build from the working directory.
- **Applying** uses `tools.apply_proposal(copy, p)` in id order. The first `ToolError` gives
  `status="error", conflict="#5 (src/a.py) no longer applies after #3"` (1.6).
- **Test command:** `tools.detect_test_cmd(root, cfg)`, run with `cwd=copy` through the same environment handling as
  `_run_command` (VIRTUAL_ENV removed).
- **Analysers:** `checks.detect(copy, paths=changed)` with each tool run separately, so each gets its own `Run` (2.3).
  The tools that need the network (semgrep with the registry config) keep their existing note.
- **Baseline (1.5):** only when a run failed. Before applying, `verify` saves the copy's original content of every
  file the proposals touch (`None` for files they create). The baseline writes those back (deleting created files),
  then runs the failing commands again.
- **`newly_failing`** compares the two outputs. For tests it collects pytest `FAILED x::y` lines, Jest `✕` lines, and
  `--- FAIL:` for go test. Otherwise it falls back to "exit changed from 0". For analysers it compares the sets of
  `path:line: message` lines with line numbers removed, because the edit moves lines.
- **Cancellation and time limits:** `cancelled()` is checked between runs. Each subprocess gets the remaining share of
  `CODEPILOT_VERIFY_TIMEOUT` (4.1). The copy is deleted in a `finally` block (4.2).

### Changes to existing modules (wiring)

- **`store.py`** gets a new table, `receipts (id, session_id, fingerprint, status, body TEXT JSON, created)`, plus
  `add_receipt(sid, receipt)`, `latest_receipt(sid)` and `mark_receipt_told(id)` (an additive column `told INTEGER`,
  for 3.5). Each receipt is about 10 KB at most, because outputs are cut to their tails.
- **`agent.py`:**
  - `Agent.verify(sid)` is a generator. It yields `verifying` (the ids), `verification` (the receipt) and `done`.
  - At the end of `_loop_steps` (the no-tool-use branch), `_verify_if_due` runs it inline before `done` when there
    are pending proposals, auto-run is on, `CODEPILOT_VERIFY` is on, and the latest receipt's fingerprint differs
    (1.1, 3.3).
  - `_turn_context` adds the latest receipt once, when it hasn't been told and still matches the pending set (3.5). A
    stale one is marked told without being sent.
  - `ToolContext` gains `cancelled`, so the tool stops between runs when Stop is pressed.
- **`tools.py`** registers `verify_changes`:
  - `needs_approval=True, auto_approvable=True` (3.2); `read_only=False`, because it runs commands.
  - It is only registered when `CODEPILOT_VERIFY` is on (4.3). Its description asks the agent to call it before ending
    a turn that leaves changes pending (3.4).
  - It marks its receipt as told, because the agent reads it in the tool result, and emits a `verification` event.
  - It shows in `describe()` as "verify pending changes: <test cmd> + analysers".
  - Its output is the receipt as text, so the agent sees which tests newly fail.
- **`server.py`:**
  - `POST /api/sessions/{sid}/verify` runs `stream(sid, agent.verify(sid))`. It is busy-guarded like chat (1.7).
  - Cancel reuses `/cancel`, which sets `_cancelled`, and `verify` passes `cancelled=lambda: sid in agent._cancelled`.
  - The session JSON gains `receipt` (the latest one), so a reload shows it.
  - At start-up, `lifespan` removes `~/.codepilot/verify/*` (4.2).
- **No mode-text change (3.4).** Mode text can't know whether `CODEPILOT_VERIFY` is on, so it could name a tool
  that doesn't exist. The request lives in the tool's description instead, which every mode that can propose changes
  sees.
- **`config.py`:** `verify: bool` (`CODEPILOT_VERIFY`, default on) and `verify_timeout: int` (`CODEPILOT_VERIFY_TIMEOUT`,
  default 600). Both go in `docs/configuration.md`.

### Front end: new `static/verify.js`

- **`receiptIsCurrent(r)`** compares the receipt's `proposal_ids` with the ids pending now. A proposal's content
  never changes, and a new version is a new id, so equal id sets mean equal fingerprints. Any difference shows the
  receipt as stale (2.2).
- **`receiptHtml()`** returns a full-width row that `renderReviewBar()` appends to `.rb-changes`, under the file names
  and buttons. The lines look like this:
  - `✓ verified · tests pass · ruff, semgrep clean · 4.1s` (green check, the existing `ok` colour)
  - `✗ 2 newly failing · test_cart.py::test_totals …` `[Details] [Ask codepilot to fix]`
  - `○ not verified` `[Verify]` / `◌ verifying… tests (12s)` `[Cancel]` / `stale: changes since` `[Re-verify]`
- **Review tab:** `renderReviewTab` puts the same line in a `.rv-receipt` row under the list header. Above `diffHtml` it puts a collapsible list of
  that file's analyser findings, matched by path prefix (2.3).
- **Chat:** `render()` handles `case "verification"` with a `details.card` in the same style as tool cards. The summary
  reads "Verified changes #1–#3: ✓ pass · 4.1s" and expands to the runs (2.4). **Details** in the bar scrolls to and
  opens that card.
- **Ask codepilot to fix** sends: "The verification of pending changes #… found these newly failing: … Fix them with
  new proposals." (2.5)

## Data models

`receipts.body` is `Receipt` as JSON. The `verification` event carries the same JSON plus `"id"`. Nothing changes for
proposals.

## Error handling

| Situation | Receipt |
|---|---|
| No test command and no analysers | `nothing`: "nothing to run; set CODEPILOT_TEST_CMD" (2.6) |
| Proposals conflict in the copy | `error` with `conflict` (1.6) |
| Clone fails (disk full, permissions) | `error`: "couldn't copy the workspace: …"; the workspace is untouched |
| Timeout | `timeout`, with the runs that finished (4.1) |
| Cancel | `cancelled`; the copy is removed (4.2) |
| Server crash mid-run | The copy is removed at the next start (4.2); no receipt, so the bar shows "not verified" |

## Testing strategy

- **`tests/test_verification.py`:**
  - Use the `repo` fixture and a fake runner.
  - Pending "a - b → a + b" turns the failing test into a pass, and the receipt is `pass` (1.3).
  - A breaking change gives `newly_failing` with the test id, and the baseline runs only on failure (1.5).
  - Conflicting proposals give `error` (1.6).
  - After any run, the workspace bytes and `git status` are unchanged (1.4).
  - The copy is gone after pass, fail, cancel and timeout (4.1, 4.2).
  - The fingerprint changes when a proposal is superseded (2.2).
  - The real `clone_tree` is tested once on a temp folder.
- **`tests/test_agent.py`:**
  - With FakeLLM, a turn ending with pending proposals and auto-run on emits `verification` before `done` (1.1).
  - It doesn't when auto-run is off (1.2) or when a matching receipt exists (3.3).
  - `verify_changes` requires approval unless auto-run is on (3.2).
  - The next `<turn_context>` includes the receipt once (3.5).
- **`tests/test_server.py`:** `/verify` returns 409 while busy; the session JSON carries the receipt.
- **`tests/e2e/test_ui.py`**, with `test_cmd` from the `repo` fixture:
  - After the "fix" turn with auto-run off, the bar shows "not verified"; Verify shows ✓ (1.2, 2.1).
  - Rejecting one change makes it stale (2.2).
  - The Review tab header shows the receipt (2.3).
  - The chat card expands (2.4).
  - A failing receipt's "Ask codepilot to fix" puts the message in the chat (2.5).
  - Timing is held back with `page.route` on `/verify` to assert the "verifying…" state deterministically (1.7).

## Alternatives rejected

- **`git worktree`:** this writes to the repo's `.git` (its `worktrees/` folder), and it misses untracked and
  uncommitted files that the tests need.
- **Applying in place, testing, then reverting:** a crash mid-test would leave unreviewed code in the workspace.
- **Verifying each proposal alone:** proposals usually depend on each other (code plus test), so a combined receipt is
  the meaningful one. The receipt lists the ids it covers.
- **Blocking Apply on failure:** this is a personal tool, and the review decision stays with me. The receipt is
  information.
