# Requirements: quick specs, length budgets and task reminders

## Introduction

CodePilot's specs follow Kiro's full flow: three documents, each written and approved in turn. The research is
consistent on where that costs more than it returns:
- In one timed trial, Spec Kit produced 2,577 lines of Markdown for 689 lines of code, and plain prompting was about
  10× faster (Scott Logic, November 2025).
- Practitioners use specs selectively, and specs that carry implementation detail go stale (CMU/Google, 2026).
- Every major framework added a fast path in 2026: Kiro Quick Spec, the BMAD scale-adaptive flow, AI-DLC Express.
- Separately, reminding agents of their plan between steps measurably reduces drift (IBM Research; abstract-level
  evidence).

This spec adds a **quick** profile with one review, length budgets for full specs, and a reminder of the current task
during long implementation turns.

Out of scope: tests linked to criteria as a gate (P1), living specs merged from change deltas (P1), and changes to
Kiro's file format.

## 1. Quick spec

**User story:** As the developer, I want a spec I review once, so that medium-sized changes get a plan without three
rounds of review.

1.1 The Specs view SHALL offer **Quick spec** next to New spec and New bugfix spec, and `/spec quick <description>` SHALL
start one. Quick specs SHALL be possible for both features and bugfixes.
1.2 WHEN a quick spec is started THEN CodePilot SHALL write all three documents in one turn: requirements (or bug
analysis), design and tasks, each short, as 1.3 sets out.
1.3 The documents of a quick spec SHALL stay within: at most 3 requirements with at most 4 criteria each; a design of
about 40 lines; at most 6 tasks.
1.4 The Spec tab SHALL show a quick spec as two steps, **Plan › Implement**. Plan SHALL show the three documents as
sub-tabs with one **Approve plan & continue** button.
1.5 WHEN I approve the plan THEN the spec SHALL move to Implement, exactly as approving the task list does today.
1.6 WHILE a quick spec has not been approved THEN **Switch to full review** SHALL turn it into a normal spec with the
documents kept, after which each phase is approved in turn.
1.7 A quick spec SHALL be stored in the same Kiro format, with `"profile": "quick"` in `spec.json`. Kiro ignores that
field.

## 2. Length budgets

**User story:** As the developer, I want specs short enough to review properly, so that I review them instead of skimming.

2.1 The instructions for each phase of a full spec SHALL ask for at most 5 acceptance criteria per requirement and
documents of at most about 150 lines, and SHALL suggest splitting the spec when more is needed.
2.2 WHEN a spec document I'm reviewing is over 200 lines THEN the Spec tab SHALL show a quiet hint with its line count:
"Long documents cost review time; consider trimming or splitting the spec."
2.3 The budgets SHALL NOT block writing or approving.

## 3. Task reminders during implementation

**User story:** As the developer, I want CodePilot reminded of its current task during long turns, so that it doesn't
drift into neighbouring work.

3.1 WHILE a spec is in Implement AND a task is in progress THEN every 6th step of a turn SHALL add a short reminder to
the tool results: task id, title, and the text of the acceptance criteria it covers.
3.2 A reminder SHALL be at most about 1,000 characters, and SHALL NOT change the system prompt.
3.3 Each reminder SHALL appear as one row in the Activity panel, and not in the chat, including after a reload.
3.4 IF no task is in progress THEN the system SHALL send no reminder.
