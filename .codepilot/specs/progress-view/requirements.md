# Requirements: progress in its own view

## Introduction

Roadmap 3, item 2. Owner, 2026-11-09: "The new progress tracker within the chat window is also a mess. It gets lost
during ongoing conversation with queued prompts. Can this be a window we go to? We can switch between that and the
folder explorer." Today a plan and a spec run are cards in the chat, with the work done under each step; as the
conversation goes on (queued prompts especially) the card scrolls away. Decided 2026-11-09: a **Progress** view in the
sidebar (as Kiro keeps a spec's tasks in a panel), a one-line marker in the chat, and the sidebar switching to it once
per run.

Out of scope: running several plans at once, the Specs view and the Spec tab (unchanged).

## 1. Progress is a sidebar view

**User story:** As the developer, I want the plan and the spec run in a place I can go to, so that they don't scroll
away while I keep talking to codepilot.

1.1 The activity bar SHALL have a **Progress** view. It SHALL show the session's plan and spec-run cards (their steps,
status, notes and the work done under each, as the chat cards do today), newest first, the live one open.
1.2 WHILE a plan or spec run is live the Progress icon SHALL show its count ("2/5"), and none otherwise.
1.3 WHEN a plan or spec run starts during a turn THEN the sidebar SHALL switch to Progress, once for that card: if the
user then picks another view, it SHALL stay there. A reload or reopening a session SHALL NOT switch.
1.4 WHILE the session has no plan or spec run the view SHALL say what will appear there.

## 2. The chat keeps one line

2.1 WHERE a plan or spec run starts, the chat SHALL show one line in its place, with its title and count ("Plan · 1 of
2 done"), kept up to date and saying how it ended, and **View progress**, which SHALL open the Progress view at that
card, opened at its step in progress.
2.2 The pinned plan line above the message box SHALL open the Progress view at the plan's card (its Continue and
Dismiss stay).
2.3 Everything the cards do today SHALL keep working from the view: the work filed under each step (and the changes'
Open and Apply), a reload drawing the same, Edit/Retry taking back what the rewound turns did (a card made after the
rewound message goes), and another session showing its own.
