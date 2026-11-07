# Requirements: the chat as readable steps, and a task card you can open

## Introduction

From the UI/UX review (Roadmap 2, item 24) and Phase 4 (items 9 and 10). Today the chat reads like a debug log:
tool names in monospace as headlines (`propose_edit`, `write_spec`), each change shown twice (the tool row, then the
change row), spec writes echoed by a chip, and a long run is one long scroll. Kiro shows each task with a spinner you
can click to see its work; Copilot opens a session's log from its row. The lesson from both, and from their issue
trackers: what the card shows must follow what actually ran, not only the model's checklist.

Out of scope: tests gating a task's "done" (item 11, its own spec next), parallel task runs, and changes to tools.

## 1. Readable steps

**User story:** As the developer, I want each step in plain words, so that I can follow a run without reading tool
names and JSON.

1.1 WHEN a tool call is shown in the chat THEN the system SHALL describe it as a verb and its object ("Read
agent/core.py", "Ran the tests", "Searched for `get_price`"), with the tool name and arguments one click away.
1.2 WHEN codepilot proposes a change THEN the system SHALL show one row for it (file, +/− counts, Apply/Reject), not a
tool row and a change row.
1.3 WHEN two or more read-only steps run in a row THEN the system SHALL group them into one row that says what they did
("Read 3 files, searched twice"), which expands to the steps.
1.4 WHEN a session is reopened THEN the system SHALL show the same rows as it did live.

## 2. A task card for plans

**User story:** As the developer, I want the plan in the chat as a card I can open step by step, so that I can see
what each step did.

2.1 WHEN codepilot starts a plan THEN the system SHALL show it as a card in the chat, listing its steps with their status.
2.2 WHILE a turn runs, the system SHALL file each tool step under the plan item in progress, and SHALL spin that item
only while the turn is running.
2.3 WHEN the user clicks a plan item THEN the system SHALL expand the steps filed under it.
2.4 The pinned plan above the message box SHALL be one line (status and progress) that scrolls to the card when clicked.

## 3. Spec runs in the chat

**User story:** As the developer, I want "Run all remaining" to show its tasks in the chat, so that I can follow and
steer a spec run without the Spec tab.

3.1 WHEN the user runs a spec's remaining tasks THEN the system SHALL show them as a task card in the chat.
3.2 WHEN a task's turn ends THEN the system SHALL mark it done, paused or failed, with its verification result if one
was made.
3.3 WHEN the user clicks a task THEN the system SHALL expand the steps that task's turn made.
3.4 The Spec tab SHALL remain the place where the documents are reviewed; the card SHALL link to it, not repeat them.
