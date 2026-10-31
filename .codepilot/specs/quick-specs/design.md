# Design: quick specs, length budgets and task reminders

## Overview

- **Profiles:** a spec gets a `profile` (`full`, the default, or `quick`). The rules that differ by profile live in a
  new `spec_profiles.py`: which documents may be written now, which phase may be approved, and the instructions.
  `specs.py`, `tools.write_spec` and the server ask it instead of hard-coding the full flow (requirement 1).
- **Budgets** are wording in the instructions, plus a hint in the browser (requirement 2).
- **Reminders** come from a new `spec_reminder.py`, called from the agent loop (requirement 3).

## Architecture

```
specs.create(profile)  ─► spec.json {"kind","approved","profile"}
specs.turn_text        ─► spec_profiles.instructions(spec)      (quick → "write all three, short")
tools.write_spec       ─► spec_profiles.may_write(spec, doc)
specs.approve          ─► spec_profiles.may_approve(spec, phase) (quick: "tasks" from the start, once all three exist)
Agent._loop_steps      ─► spec_reminder.due(step) → spec_reminder.text(spec) → appended to the last tool result
```

### New: `codepilot/spec_profiles.py`

Its one reason to change is how much ceremony a spec gets. It knows nothing about files.

```python
PROFILES = ("full", "quick")

def may_write(profile: str, phase: str, doc: str) -> bool
    # full: doc's index <= phase's index (today's rule); quick: any of the three while phase == "requirements"
def may_approve(profile: str, phase: str, target: str, docs_present: set[str]) -> str | None   # None = ok, else why
    # full: today's rule; quick: target == "tasks" and all three docs present ("Approve plan")
def instructions(profile: str, kind: str, phase: str) -> str
    # full: today's PHASE_INSTRUCTIONS text plus the budget sentence (2.1)
    # quick + requirements: QUICK_FEATURE or QUICK_BUGFIX (1.2, 1.3); quick + implement: today's text
def can_switch_to_full(approved: str) -> bool   # only before any approval (1.6)
def requested(text: str) -> tuple[str, str]     # "quick add x" -> ("quick", "add x"); otherwise ("full", text)
```

The `PHASE_INSTRUCTIONS` dictionary moves from `specs.py` into this module, unchanged apart from the budget sentence.
`specs.turn_text` calls `instructions()`. The quick text ends: "Ask the user to review the plan and approve it in the
Spec tab."

### New: `codepilot/spec_reminder.py`

Its one reason to change is what the agent is reminded of mid-turn.

```python
EVERY = 6
MAX_CHARS = 1000

def due(step: int) -> bool                                  # step % EVERY == 0
def criteria(requirements_md: str, ids: list[str]) -> dict  # "1.2" -> the criterion line (lines starting "1.2 ")
def current(spec: Spec) -> Task | None                      # the innermost task in progress
def text(spec: Spec) -> str | None                           # None when no task is in progress (3.4)
    # '<spec_reminder spec="x" task="2.1">Current task 2.1: Add write_csv. Criteria it must satisfy:
    #  1.1 WHEN … Stay on this task; don't start the next one.</spec_reminder>'
```

### Changes to existing modules (wiring)

- **`specs.py`:**
  - `Spec` gains `profile: str = "full"`, which `_load` reads from `spec.json`.
  - `create(root, name, kind, profile="full")`.
  - `approve` delegates its checks to `may_approve`. A quick approval writes `approved="tasks"`, so the spec's `phase`
    becomes `implement` (1.5).
  - `set_profile(root, spec, "full")` is guarded by `can_switch_to_full` (1.6).
  - `info()` includes `profile`.
- **`tools.py`, `write_spec`:** uses `may_write`. The error text stays "The spec is in the … phase; the user approves it
  before you write …".
- **`server.py`:**
  - `POST /specs` accepts `profile`.
  - `spec_action` gains `profile` (`{"profile": "full"}`) for 1.6.
- **`agent.py`:**
  - `_spec_for_message` and `/spec` parsing accept a leading `quick` (1.1). The existing bug-word detection still picks
    the kind.
  - In `_loop_steps` and `resume`, just before the results are stored: if the session's active spec is in `implement` and
    `spec_reminder.due(steps)`, append the reminder to the last tool result's content and yield
    `{"type": "spec_reminder", "task": id}` (3.1, 3.3). The frozen system prompt is untouched (3.2).
    - `steps` is counted on the turn with `_turn_flag`, not by the loop: approvals restart the loop, so a task that
      keeps pausing would otherwise never reach step 6.
    - It's a block inside the tool result, not a text block beside it: a text block in a user message reads as the
      user speaking to compaction, turn costs and the transcript. Old reminders are also pruned with their output.
  - `history_events` leaves reminders out of the tool output it redraws (3.3).

### Front end: new `static/specs-quick.js`

- **Specs view:** `renderSpecs` gets a **Quick spec** button between New spec and New bugfix spec. It calls
  `newSpec("feature", "quick")`, and the dialog hint reads "One review: codepilot drafts requirements, design and tasks
  together." Spec rows of quick specs show a `quick` tag in the existing `.incl` style.
- **Spec tab:** `renderSpecTab` asks `quickSteps(spec)` for the stepper when `spec.profile === "quick"`.
  - The steps are **Plan › Implement**.
  - Plan's body has three sub-tabs, using the `.sp-step` button style at a smaller size.
  - The doc bar has **Approve plan & continue**, which calls `approveSpec(spec, "tasks")`, and **Switch to full
    review**.
  - `approveSpec` already treats `tasks` as the last approval and shows "Task list approved…" (1.4, 1.5).
  - After switching to full review, approving a phase whose next document already exists just shows it: asking for it
    to be written again would throw away the document 1.6 keeps.
- **Length hint:** after loading a document, `renderSpecTab` counts lines. Over 200, it adds
  `<div class="hint sp-tip">` with the 2.2 text, using the same style as the existing auto-apply tip (2.2).
- **Activity:** `render()` handles `case "spec_reminder"` with `activity("model", "spec", "reminder: task " + ev.task)`
  only (3.3).

## Data models

`spec.json` becomes `{"kind": "feature", "approved": "", "profile": "quick", "created": …}`. A missing profile means
`full`, so every existing spec is unaffected.

## Error handling

- Approving the plan before all three documents exist: 409 with "Write the design and tasks first (or ask codepilot to
  finish the plan)."
- Switching to full after approval: 409 with "Already approved; it's past planning."
- A requirements document with no matching criterion line: the reminder lists only the task id and title.
- A hand-edited `spec.json` with an unknown profile: treated as `full`.

## Testing strategy

- **`tests/test_specs.py`:**
  - `may_write`, `may_approve` and `can_switch_to_full` tables for both profiles (1.2, 1.5, 1.6).
  - `create` with `profile`.
  - Old `spec.json` files without `profile` load as full (1.7).
  - Quick instructions contain the budgets (1.3); full instructions contain the 2.1 sentence.
  - `spec_reminder.criteria` parsing and `text` length cap and `None` when no task is in progress (3.1, 3.2, 3.4).
- **`tests/test_tools.py`:** `write_spec` accepts design and tasks in quick requirements, and refuses them in full.
- **`tests/test_agent.py`:**
  - A FakeLLM implement turn of 12 steps gets exactly two reminders, in tool results, never in `system` (3.1, 3.2).
  - A `spec_reminder` event is emitted.
- **`tests/test_server.py`:** profile on create; the `profile` action, and its 409.
- **`tests/e2e/test_ui.py`**, with ScriptedLLM extended to write all three documents when the turn's `<spec>` block says
  quick:
  - Quick spec → Plan with three sub-tabs → Approve plan → Implement (1.1, 1.4, 1.5).
  - Switch to full shows three steps (1.6).
  - A 250-line document shows the hint (2.2).

## Alternatives rejected

- **A fourth phase constant `plan`.** It would ripple through `PHASES` and the stepper code. Keeping the phases and
  changing only the approval rule is smaller.
- **Choosing quick or full automatically from the description's length.** It is unpredictable. I'd rather choose.
- **Putting reminders in the system prompt.** That would break prompt caching and reasoning replay (architecture.md).
