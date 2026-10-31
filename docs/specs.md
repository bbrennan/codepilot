# Specs: spec-driven development

For bigger changes, plan before coding. A **spec** takes a feature (or a bug) through three short,
reviewable documents:

1. **requirements** (what): user stories with testable acceptance criteria
2. **design** (how): architecture, interfaces, data, errors, testing
3. **tasks** (steps): small coding tasks, each tied to the criteria it satisfies

Then codepilot **builds it task by task**. You approve each document before the next is written, so
misunderstandings surface while they're cheap to fix.

Specs use **Kiro's file format** and live in `.codepilot/specs/`. Only those are listed: other tools' spec
folders (`.kiro/specs/`, Spec Kit's `specs/`) belong to those tools, so codepilot leaves them out.

- [When to use a spec](#when-to-use-a-spec)
- [Walkthrough](#walkthrough)
- [Quick specs](#quick-specs)
- [Bugfix specs](#bugfix-specs)
- [The files](#the-files)
- [Running tasks](#running-tasks)
- [Keeping the spec honest](#keeping-the-spec-honest)
- [How it works](#how-it-works)

## When to use a spec

Use a spec for **multi-file features, cross-cutting changes, and bugs whose cause isn't obvious**. For a
one- or two-file change, plain Build mode is faster. Industry experience is consistent on this: specs pay
off on larger work and are overhead on small fixes.

## Walkthrough

1. **Start.** Open the **Specs** view (the list icon in the activity bar) → **New spec**. Describe what you
   want in a sentence or two, and confirm the name (e.g. `csv-export`). Alternatively, switch the chat to
   **Spec** mode and just type the request; codepilot creates the spec from it.
2. **Requirements.** codepilot investigates the code and writes `requirements.md`. Each requirement is a
   user story with numbered acceptance criteria in **EARS** form:
   ```
   1.1 WHEN the user clicks Export THEN the system SHALL download a CSV of the visible rows.
   1.2 IF the report has more than 100,000 rows THEN the system SHALL stream the file.
   ```
   It appears in the **Spec** tab. Read it, then:
   - **Approve requirements & continue**;
   - or type what to change under it ("1.2 should also apply to PDF");
   - or click **Edit** and change it yourself.
3. **Design.** codepilot writes `design.md`: components and real files, interfaces, data models, error
   handling and a testing strategy, traced to requirement numbers. Review and approve it the same way.
4. **Tasks.** codepilot writes `tasks.md`: a checklist of small coding tasks, test-first where practical,
   each listing the requirements it covers. Approve it.
5. **Implement.** The **Implement** step lists the tasks. Click **Run** on one, **Run next task**, or
   **Run all remaining**. codepilot works on that task only, writes the tests for its criteria first, and
   ticks it off when they pass.

Until the task list is approved, codepilot can't propose code changes in a spec. The planning phases plan.
Click any finished step in the stepper to look back at its document.

## Quick specs

For a medium-sized change that deserves a plan but not three rounds of review, use a **quick spec**: **Specs → Quick
spec**, `/spec quick add CSV export`, or in Spec mode a first message starting with `quick`. It works for bugs too: the
kind comes from your description.

codepilot writes all three documents in one turn, kept short: at most 3 requirements with 4 criteria each, a design of
about 40 lines, and at most 6 tasks. The Spec tab shows two steps, **Plan › Implement**, with the documents under Plan
and one **Approve plan & continue**. From there it's the same as any spec.

If the plan needs a closer look, **Switch to full review** before approving. The documents are kept, and you approve
each in turn. Quick specs use the same files, with `"profile": "quick"` in `spec.json`.

**Length.** Full specs are asked to stay under about 150 lines per document and 5 criteria per requirement, and to
suggest splitting when more is needed. A document over 200 lines shows a quiet hint with its length. Neither blocks
anything: they're there because a spec too long to review doesn't get reviewed.

## Bugfix specs

**New bugfix spec** replaces requirements with a **bug analysis** (`bugfix.md`):
- Current behaviour, with reproduction steps;
- Expected behaviour, as EARS criteria;
- Root cause, confirmed or clearly marked as a hypothesis;
- Unchanged behaviour: what must keep working (the regression criteria).

Design and tasks follow as usual. In Spec mode, a message that describes a bug ("fails", "wrong",
"crash", …) starts a bugfix spec automatically.

## The files

```
.codepilot/specs/csv-export/
  requirements.md   (bugfix.md for bugfix specs)
  design.md
  tasks.md          - [ ] 1. Title / - [-] 2.1 in progress / - [x] 3. done, with _Requirements: 1.1_ lines
  spec.json         codepilot's bookkeeping: kind, profile and the last approved phase
```

They're plain Markdown: commit them, review them in pull requests, edit them anywhere. Because the format is
Kiro's, a spec can be copied between `.codepilot/specs/` and `.kiro/specs/` by hand.

## Running tasks

During a long task, codepilot is reminded what it's working on: every 6th step of a turn, the task in progress and the
text of its acceptance criteria are added to the latest tool result, so it doesn't drift into neighbouring work. Each
reminder is a row in Activity, not in the chat.

- **Run** (or **Run next task**) sends "Implement task 2.1 of spec csv-export: …". The message carries the
  requirements, design and task list, so codepilot has them even in a long session.
- **Run all remaining** runs tasks one after another. It pauses when a command needs approval, when
  changes are waiting for your review, or when a task didn't get marked done. Press **Run next task** to
  continue.
- **Auto-apply edits** (the switch under the message box) lets changes land without review so tasks run
  back to back. Every change can still be undone in **Changes**. Without it, review each task's changes in
  the review bar, and runs pause for you.
- With **Auto** model routing, implementation runs on the newest Sonnet and the planning phases on Opus.

## Keeping the spec honest

Specs go stale when code moves on. On the Implement step:
- **Check spec vs code** has codepilot compare them. It lists criteria not (fully) implemented, behaviour
  the spec doesn't describe, and done tasks whose code doesn't match. Where the code is right, it updates
  the spec; it asks before changing code.
- **Verify with evals** (shown when `CODEPILOT_EVAL_CMD` is set, e.g. `make evals`, `npm run e2e` or an
  LLM eval suite) runs that command and maps the results to the acceptance criteria. For each criterion it
  shows which scenarios, test cases or traces exercise it and whether they pass. It also lists criteria
  with no coverage and suggests new scenarios. This closes the loop from requirement to observed
  behaviour, for any app with an end-to-end or eval suite.

## How it works

- **Spec mode** is a built-in mode. In it, each message carries a `<spec>` block with the current phase's
  instructions and the spec documents so far.
- **Two tools:** `write_spec` writes the active spec's documents (no approval needed; they're docs, and you
  approve the phase). `update_task` ticks tasks.
- **Guardrails:** `write_spec` can't write a phase you haven't reached, and approving never skips ahead or
  moves back. In a quick spec, all three documents can be written during planning and are approved together. Until
  tasks are approved, `propose_edit` is refused in a spec session.
- **Endpoints:** `GET/POST /api/sessions/{sid}/specs` and `POST /api/sessions/{sid}/specs/{name}/approve`
  (or `/activate`, or `/profile` with `{"profile": "full"}`).
