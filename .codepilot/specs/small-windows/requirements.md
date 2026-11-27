# Requirements: small windows

## Introduction

Roadmap 4, item 3. From the UI review of 2026-11-26, at 1024×700 with the sidebar, editor and chat all open: the editor
is 281px wide, its toolbar shows "Add to chat" and "Ask" and cuts off **Edit**, copy and reload; the terminal's toolbar
cuts off new, rename and kill; "ACTIVITY 36" wraps onto two lines. At 600px wide the title bar loses the theme and help
buttons and the page scrolls sideways.

`layout.js` already fits saved pane sizes to the window (#56), but it protects only a 280px editor, and nothing lets a
toolbar get by with less room.

Out of scope: a phone layout; windows under 480px wide; hiding the chat automatically.

## 1. Toolbars keep all their controls

**User story:** As the developer on a laptop screen, I want every toolbar button to stay reachable, so that a narrow
pane never takes a feature away.

1.1 The editor's toolbar SHALL show all its controls at every editor width from 280px: below a set width its buttons
SHALL show icons without labels, each with a tooltip, and the path SHALL be what is shortened.
1.2 The terminal's toolbar SHALL show all its controls at every panel width from 280px, on the same rule; the working
folder's path SHALL be what gives way.
1.3 The bottom panel's tabs SHALL keep each count beside its label at every panel width from 280px.
1.4 The title bar SHALL keep every button on screen down to a 480px window, and the page SHALL NOT scroll sideways.

## 2. Room for the editor

**User story:** As the developer, I want the editor to keep a usable width when the window is small, so that I can read
code without closing panes by hand.

2.1 WHEN the window can't fit the saved pane sizes THEN the sidebar and chat SHALL shrink, toward their minimum widths,
before the editor goes under 440px.
2.2 IF the editor would be under 400px even with both at their minimums THEN the sidebar SHALL be hidden for as long as
the window is that small, without changing the saved choice; WHEN the window grows it SHALL be shown again.
2.3 IF the user shows the sidebar themselves while it is hidden this way THEN it SHALL stay shown until the window is
next resized.
2.4 Saved pane sizes SHALL be untouched by any of this, and come back when the window is large again, as today.
