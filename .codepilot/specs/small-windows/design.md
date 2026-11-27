# Design

Checked against the code after items 1 and 2 merged (#116–#125); things are named, not numbered by line.

## Toolbars: icons when there's no room for words (1.1–1.3)

CSS container queries; no measuring in JavaScript.

- `app.css`: `.editor { container: editor / inline-size; }`, `.panel { container: panel / inline-size; }`.
- Button text moves into `<span class="lbl">` (`lbl()` beside `icon()` in `app.js`) in the toolbar templates:
  `renderFileTab`, `renderDocTab`, `renderEditTab`, `renderImageTab`, `renderTraceTab`, the spec tab's steps
  (`renderSpecTab`, and `quickSteps` in `specs-quick.js`), `viewSwitch`, and `#termSendSel` and `#termRestart` in
  `index.html`. Each such button gets a `title` where it has none, so the icon has a tooltip. A text-only button gets
  an icon: Done (`x`), Preview and Source (`eye`, `file`), `#termSendSel` (`chat`), `#termRestart` (`refresh`).
- A hidden label is hidden visually only (clipped to 1px, not `display: none`), so the accessible name is unchanged.
- `renderBinaryTab` (`filekinds.js`, new in #120) has one icon button (Copy path) with a title: nothing to change, and
  it is tested with the rest. `renderGitDiffTab` has one icon button. `renderDiffTab` is the dead `diff` tab kind
  (noted in ROADMAP's loose ends) and is left alone.
- **The Review header keeps its words.** Apply, Reject (or Undo) and Open file already wrap as one group under a long
  path (#121), and the header is the Review's own (task 4), so it gets no `.lbl` spans.
- The line count, the edit state, an image's size and a trace's size get class `ed-count`; that is what the compact
  rule hides. `.ed-bar > .muted` would also hide "read-only" and the Review's reason.

The thresholds are measured, not estimated: Chrome 158 on macOS, the path held at its 60px floor, with Verdana standing
in for CI's wider Linux font (DejaVu Sans). With words, a toolbar needs:

| toolbar | system font | Verdana |
|---|---|---|
| a markdown file in Source (Add, Ask, Preview/Source, Edit, copy, reload) | 582 | 596 |
| a spec's steps (four) | 482 | 493 |
| a markdown file in Preview | 460 | 475 |
| a trace ("Ask codepilot about this trace") | 443 | 471 |
| a file | 446 | — |
| the terminal, its folder's path at 0 | 382 | 388 |
| the panel's tabs | 321 | 339 |

So one 520px threshold would cut off a markdown toolbar between 521 and about 600. The queries are:

- `@container editor (max-width: 640px)`: a toolbar with the Preview/Source switch (`.ed-bar:has(.seg)`) hides its
  buttons' words and its line count; its path's floor drops to 40px.
- `@container editor (max-width: 520px)`: every editor toolbar hides its buttons' words and the spec steps' words
  (the step keeps its number or tick). Icon buttons get `padding: 0 7px`.
- `@container editor (max-width: 420px)`: compact. Gap 4px, padding 8px, icon buttons `0 5px`, path floor 40px, the
  `ed-count` hides, and the Preview/Source switch shows icons. With words, that switch needs about 425px beside the
  markdown toolbar's five icon buttons; at 280px with icons, the toolbar needs 268px.
- `@container panel (max-width: 420px)`: the terminal's toolbar hides its buttons' words and the folder's path
  (which is already the first to give way: it shrinks with an ellipsis), and `.term-select { min-width: 0; flex: 0 1
  110px; }`.
- `.panel-tabs { overflow-x: auto; scrollbar-width: none; } .panel-tabs > button { white-space: nowrap; flex: none; }`
  (1.3). No threshold: the row fits until about 340px, and under that it scrolls sideways rather than wrap, at any
  width. The tabs are what matter; Clear and Close scroll into reach (Close is also ⌘J and the title bar's toggle).

## Title bar (1.4)

At 600 and 480 wide the page was 681–736px wide: the title bar's own content, and the status bar's seven items. The
title bar's icon buttons were also squashed to 16px before anything else gave way.

In the existing `@media (max-width: 820px)` block: `.menu-btn span:not([data-icon])` hidden (File and Terminal show
their icon and caret), `.titlebar { gap: 4px; }`, `.titlebar > button { flex: none; }` except `.workspace-btn
{ min-width: 0; flex: 0 1 auto; }`, which shrinks first. The word "codepilot" moves into `<span class="brand-name">`,
hidden at 560px and under: there the folder's name keeps at least 100px. The status bar hides the test command, the
GitHub login and the token count (the least used), and its items may shrink. The stacked layout's `body { overflow:
auto }` stays for the vertical scroll; `overflow-x: hidden` is not used to hide a real overflow: the test asserts
there is none.

## Fitting panes (`layout.js`)

- `LAYOUT.CENTER_COMFORT = 440`, `CENTER_FLOOR = 400`. `layoutRoom` takes the editor's width to protect; `fitLayout`
  passes `CENTER_COMFORT` when sharing out a shortfall; dragging a resizer still stops at `CENTER_MIN` (280): a size
  you drag to is your choice (until the next fit). The grid's `minmax(280px, 1fr)` is unchanged.
- **Whether the sidebar steps aside is decided from the window width, the pane minimums and your own show/hide
  choice, as if the sidebar were shown; never from what is shown now.** Hiding the sidebar frees room, so a rule that
  looked at the room left would show it again, and the `MutationObserver` re-runs `fitLayout` on every class change:
  it would oscillate. `layoutSidebarSteps(ide)` is true when the layout is not stacked (`matchMedia("(max-width:
  820px)")`, the CSS's own query), you haven't hidden the sidebar (`no-sidebar`), you haven't shown it since the last
  resize (`LAYOUT.keepSidebar`), and `innerWidth - ACTIVITY_W - RESIZER - sidebar min - (chat shown ? RESIZER + chat
  min : 0) < CENTER_FLOOR`. With the chat shown that is a window under 936px: the 821–935px band. With the chat
  hidden it is under 632px, which is the stacked layout, so never.
- `fitLayout` sets class `auto-no-sidebar` on `#ide` from that, adding or removing it only when its value changes (a
  class write with the same value would still notify the observer). `layoutRoom` and `fitLayout` count
  `auto-no-sidebar` as hidden (`layoutShown(ide, "sidebar")`). `app.css` treats `.ide.auto-no-sidebar` exactly as
  `.ide.no-sidebar`. Nothing is written to `localStorage`.
- 2.3: `layoutUserShowedSidebar(ide)` sets `LAYOUT.keepSidebar = true`, removes `auto-no-sidebar`, and returns whether
  the sidebar was hidden this way. `app.js` calls it from `setView(…, reveal)` (an activity-bar icon, Reveal in
  Explorer) and from a `toggleSidebar()` used by the title-bar button and ⌘B: when the sidebar was hidden for room,
  the toggle shows it and saves nothing; otherwise it toggles `no-sidebar` as before. The activity bar's "click the
  active icon to collapse" asks `layoutShown(ide, "sidebar")`, so on a sidebar hidden for room it shows it instead of
  saving "hidden". The `resize` listener clears `keepSidebar` before fitting.

With the default sizes (280 and 440) at 1024px: room for the panes is 1024 − 48 − 8 − 440 = 528, the shortfall of 192
is shared by slack (100 and 140), giving a 200px sidebar, a 328px chat and a 440px editor. The message box at 328px
relies on ui-review-fixes task 1 (the busy row wraps). At 900px the sidebar steps aside and the chat takes 408px.

## The Review tab in a narrow editor (1.5)

`.review` is a two-column grid whose change list takes up to 280px, so in a 440px editor the diff got about 160px.
`@container editor (max-width: 640px)`: `.review` becomes a column; `.rv-list` is at most 30% of its height (40% left the diff shorter than the list with the bottom panel open) (it
scrolls), with a bottom border instead of a right one; `.rv-main` takes the rest. At 640px side by side the diff would
get 360px, about what its header needs to keep the path, the reason and Apply, Reject and Open file on one row.
j/k and the header are unchanged.

## Menus and `container-type`

`container-type: inline-size` can make `.editor` and `.panel` the containing block for `position: fixed`
descendants, depending on the Chrome version. None are inside them: `#ctxMenu` (the editor's context menu, the
terminal's ⋯ menu), the palette, dialogs and toasts are all at the end of `<body>`, outside `#ide`. Checked in the
real UI at 1024×700: the breadcrumb's context menu and the terminal's ⋯ menu open at the pointer and the button.

## Decisions

- **Icons before a "more" menu.** An overflow menu needs measuring, a second place for every action and its own
  keyboard handling. Five icon buttons fit in 280px.
- **The chat is never hidden for you.** It is where approvals arrive; a hidden approval looks like a stuck session.
- **The sidebar hides only in the 821–935px band**, where the arithmetic leaves no other choice.

## Tests

Dragging the chat's edge is the only way to an editor under 440px (fitting gives it 440 from saved sizes), so the
toolbar tests drag; the rest set sizes through `localStorage`. All assert geometry.

- `tests/e2e/test_narrow_panes_ui.py`: every editor toolbar kind (file, markdown Source and Preview, editing,
  trace, binary, spec) keeps every control inside its bar and hit-testable, each with a tooltip, at 641/639,
  521/519, 421/419 and 280px, with words shown or hidden as the thresholds say; the terminal's toolbar at 421/419 and
  280; the panel's tabs one line each at 280; at 1024×700 the file and terminal toolbars, with the words still naming
  the buttons; the Review at 1024×700 with "fix two" (list above and shorter, buttons in the header, j/k), and at
  641/640.
- `tests/e2e/test_window_fit_ui.py`: the title bar at 600, 561, 559 and 480 (no sideways scroll, every button on
  screen at full size, the folder ≥ 100px, the word "codepilot" only above 560); the editor ≥ 440 at 1024×700, also
  with an 820px chat saved (still saved); `auto-no-sidebar` at 935 and 821, not at 936 or 820; at 900 it settles (no
  class or size change for a second) and the sidebar is back at its saved width at 1440; showing it yourself (button,
  ⌘B, the active or another activity icon) wins through opening a file, until a resize; hiding it yourself is saved.
