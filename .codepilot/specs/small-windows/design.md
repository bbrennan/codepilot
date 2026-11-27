# Design

## Toolbars: icons when there's no room for words (1.1–1.3)

CSS container queries; no measuring in JavaScript.

- `app.css`: `.editor { container: editor / inline-size; }`, `.panel { container: panel / inline-size; }`.
- Button text moves into `<span class="lbl">` in the toolbar templates (`renderFileTab`, `renderDocTab`,
  `renderEditTab`, `renderImageTab`, `renderTraceTab`, `renderSpecTab`, the Review header, `#termSendSel` in
  `index.html`). Each such button gets a `title` equal to its label where it has none, so the icon has a tooltip and
  the accessible name is unchanged. `#termSendSel` gets an icon (`chat`) for its short form.
- `@container editor (max-width: 520px) { .ed-bar .lbl { display: none; } .ed-bar .btn { padding: 0 7px; } }`. The
  line/selection count (`.ed-bar > .muted`) hides under 400px. `.crumbs` already truncates.
- `@container panel (max-width: 520px) { .term-bar .lbl, .term-cwd { display: none; } .term-select { min-width: 0;
  flex: 0 1 110px; } }`.
- `.panel-tabs > button { white-space: nowrap; }` (1.3); under 360px the tab row scrolls sideways rather than wraps.

The view/Preview switch (`.seg`) keeps its words: two short labels that are the control.

## Title bar (1.4)

In the existing `@media (max-width: 820px)` block: `.menu-btn span:not([data-icon]):not(.caret) { display: none; }`,
`.palette-btn` icon only (already at 1100px), `.workspace-btn { max-width: 34vw; min-width: 0; }`, `.titlebar { gap:
4px; }`, `.brand` text hidden under 560px. The stacked layout's `body { overflow: auto }` stays for the vertical
scroll; `overflow-x: hidden` is not used to hide a real overflow: the test asserts there is none.

## Fitting panes (`layout.js`)

- `LAYOUT.CENTER_COMFORT = 440`, `CENTER_FLOOR = 400`. `layoutRoom` and `fitLayout` use `CENTER_COMFORT` where they use
  `CENTER_MIN` today when sharing out a shortfall; dragging a resizer still stops at `CENTER_MIN` (280): a size you
  drag to is your choice. The grid's `minmax(280px, 1fr)` is unchanged.
- After sharing the shortfall, if both panes are at their minimums and
  `innerWidth - ACTIVITY_W - resizers - side - chat < CENTER_FLOOR`, `fitLayout` adds class `auto-no-sidebar` to
  `#ide`; otherwise it removes it. `app.css` treats `.ide.auto-no-sidebar` exactly as `.ide.no-sidebar` (add it to
  those selectors). Nothing is written to `localStorage`.
- 2.3: `layoutUserShowedSidebar()` (called from `toggle("no-sidebar")` and `setView(…, reveal)` in `app.js`) sets
  `LAYOUT.keepSidebar = true` and removes the class; the `resize` listener clears `keepSidebar` before fitting.
- The `MutationObserver` on `#ide`'s class already re-runs `fitLayout`; adding or removing `auto-no-sidebar` only when
  its value changes keeps that from looping.
- Under 821px the stacked layout applies and `fitLayout` leaves `auto-no-sidebar` off.

With the default sizes (280 and 440) at 1024px: room for the panes is 1024 − 48 − 8 − 440 = 528, the shortfall of 192
is shared by slack (100 and 140), giving a 200px sidebar, a 328px chat and a 440px editor. The message box at 328px
relies on ui-review-fixes task 1 (the busy row wraps).

## Decisions

- **Icons before a "more" menu.** An overflow menu needs measuring, a second place for every action and its own
  keyboard handling. Five icon buttons fit in 280px.
- **The chat is never hidden for you.** It is where approvals arrive; a hidden approval looks like a stuck session.
- **The sidebar hides only in the 821–935px band**, where the arithmetic leaves no other choice.

## Tests

`tests/e2e/test_window_fit_ui.py` (existing; it already sets saved sizes through `localStorage`):
- 1024×700, default sizes, a file open and the terminal shown: `#fEdit`, `#fCopy`, `#fReload` are inside `.ed-bar`'s
  rect and hit-testable; `#termNew`, `#termRename`, `#termKill`, `#termMore` inside `.term-bar`; each has a `title`;
  the editor is at least 440px wide; each `.panel-tabs` button is one line high (1.1–1.3, 2.1).
- the same with the chat dragged to its 820px maximum: the saved size is unchanged in `localStorage`, the editor ≥ 440.
- 900×700: `#ide` has `auto-no-sidebar`, `cp-no-sidebar` is not "1"; resize to 1440: the sidebar is back at its saved
  width (2.2, 2.4); at 900 click an activity-bar icon: the sidebar shows and stays through a file opening; a resize
  hides it again (2.3).
- 600×800 and 480×800: `documentElement.scrollWidth <= clientWidth`; `#themeBtn` and `#helpBtn` are in view (1.4).
