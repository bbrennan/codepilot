# Design

## Where it lives

- `codepilot/static/sessions.js` (new): how sessions are listed and found. `sessionMatches(s, q)` (1.2, 2.1),
  `sessionGroups(list)` (2.2), `renderSessionList(list)` (the sidebar, with its search box), and the switcher:
  `openSwitcher()`, `closeSwitcher()`, keyboard and clicks (1.1–1.4). Loaded after `app.js`.
- `static/app.js` (wiring only): `loadSessions` hands the list to `renderSessionList`; the default view is
  `sessions` (2.3). The chat title becomes a button that opens the switcher.
- `static/index.html`: the title button (`#chatTitle` keeps the text, inside `#chatTitleBtn`), the sidebar's search box,
  the switcher's popover (`#sessPop`) under the chat header.
- `static/app.css`: the button, popover and group headings.

No server change: `GET /api/sessions` already returns each session's title, folder, age and busy flag.

## Decisions

- A popover under the chat header, not the command palette: it's where you're looking, and it shows the folder and age
  the palette's file rows don't have.
- Groups are ordered by their newest session, and sessions by age within a group, so the session you just used is
  always at the top of the sidebar.
- The existing click handlers (open, delete) stay on the rows; filtering hides rows rather than re-rendering, so a
  search survives the 4-second refresh while a session works.

## Tests

E2E (Playwright): the title opens the list with the open session marked; typing filters by title and by folder; Enter
and a click open a session; Escape closes; New session is first; the sidebar groups by folder and filters; a first
visit shows Sessions.
