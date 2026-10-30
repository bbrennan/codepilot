# Requirements: turn checkpoints

## Introduction

Edit and Retry rewind the conversation but leave applied file changes in place. `/undo` reverts one change at a
time. So after a turn goes wrong, I undo each change by hand in **Changes** before trying again. This spec ties a
turn's file changes to the turn: rewinding can restore the files the rewound turns changed, and any turn's changes
can be undone in one action.

**In scope:** changes CodePilot applied through proposals, whether reviewed or auto-applied. Both are already
recorded with before/after text.

**Out of scope:**
- Files changed by `run_command`, the terminal, the Explorer or another editor. They were never tracked, and the
  confirmation says so.
- Git operations. CodePilot still never commits or switches branches.
- Undoing a revert ("redo").

## 1. Restore files when rewinding

**User story:** As the developer, I want Edit and Retry to offer to undo the file changes made after that message, so
that the code and the conversation go back together.

1.1 WHEN I edit or retry a message AND changes were applied at or after it THEN the system SHALL ask for confirmation,
listing those changes (path and change number), with an option "Also undo these N file changes" that is ticked by
default.
1.2 WHEN I confirm with the option ticked THEN the system SHALL revert the listed changes newest first, mark each one
`reverted`, and then rewind and resend as today.
1.3 WHEN I confirm with the option unticked THEN the system SHALL rewind the conversation only, as today.
1.4 WHEN no applied change comes at or after the message THEN the system SHALL behave exactly as today.
1.5 IF a listed change can't be reverted because its file changed since it was applied THEN the confirmation SHALL show
it as "changed since, left as is" before I confirm, and the system SHALL revert the rest.
1.6 WHEN the rewind finishes THEN the chat SHALL show one line saying how many files were restored and which were left.
1.7 The confirmation SHALL say that changes made by commands, the terminal or other editors are not undone.

## 2. Undo a turn's file changes without rewinding

**User story:** As the developer, I want to undo everything CodePilot applied from a message onwards while keeping the
conversation, so that it can try again knowing what didn't work.

2.1 WHEN I hover over a message that started a turn AND changes were applied at or after it THEN the system SHALL show
an **Undo file changes from here** action next to Edit and Retry.
2.2 WHEN I choose it THEN the system SHALL show the list described in 1.1 and 1.5 and, when I confirm, revert as in 1.2,
leaving the conversation unchanged.
2.3 WHEN changes have been reverted this way THEN the assistant SHALL be told on my next message which changes I
reverted, through the existing proposal-outcome notes.
2.4 WHILE CodePilot is working on this session THEN the system SHALL refuse both actions with the existing message
"Wait for codepilot to finish (or press Stop) first."

## 3. Safety

3.1 The system SHALL write a file only if its current content is exactly what the change being reverted wrote (the
existing undo guard), and SHALL delete a file only if that change created it.
3.2 WHEN several listed changes touch the same file THEN the system SHALL revert them newest first. IF a newer change on
that file can't be reverted THEN the system SHALL also leave every older change on that file as is.
3.3 The system SHALL revert only the changes shown in the confirmation I accepted, even if another change was applied
in the meantime.
3.4 IF reverting a change fails partway (for example, a permission error) THEN the system SHALL stop, report what was
restored and what wasn't, and leave the conversation un-rewound.
