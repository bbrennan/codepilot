# Requirements: getting to your sessions

## Introduction

Roadmap 3, item 1 (owner's feedback, 2026-11-09): "I have to click the + for create new session before I can see the
session history." The Sessions list is behind the clock icon in the activity bar, the sidebar opens on the Explorer,
and the only other way to a past session is the welcome page, which shows when no file is open (after **+**, say).
Nothing in the chat says there are other sessions or lets you switch.

Out of scope: several folders in one session (item 2), renaming or pinning sessions.

## 1. Switch from the chat

**User story:** As the developer, I want to switch sessions from where I'm chatting, so that past work is one click
away.

1.1 WHEN the user clicks the chat's title THEN the system SHALL show a list of sessions, most recently used first, each
with its title, folder and age, and the one open marked.
1.2 WHEN the user types in that list's search box THEN the system SHALL show only the sessions whose title or folder
contains the text (ignoring case), and Enter SHALL open the first one shown (or the one picked with ↑/↓).
1.3 WHEN the user picks a session THEN the system SHALL open it and close the list; Escape or a click outside SHALL
close it without change.
1.4 The list SHALL start with **New session**, and a session that's working SHALL show a spinner.

## 2. A Sessions sidebar you can find your way in

2.1 The Sessions view SHALL have a search box that filters as in 1.2.
2.2 The Sessions view SHALL group sessions by folder, under the folder's name, with the group of the newest session
first; sessions with no folder SHALL be grouped under "No folder".
2.3 WHEN codepilot opens with no sidebar view remembered (the first time) THEN the sidebar SHALL show Sessions.
