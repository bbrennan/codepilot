# Design

## One module: `static/a11y.js` (new, loaded after `app.js`)

The app redraws by replacing `innerHTML`, so roles and tab stops written into each template would touch every render
function in `app.js`. Instead `a11y.js` decorates what was rendered, keyed by selectors, and owns all the key handling.
Adding a new kind of row is adding a selector.

| Part | What it does |
|---|---|
| `ACTIVATABLE` | Selectors for click-only elements (`A11Y_BUTTONS`, `A11Y_LINKS`): `.session`, `.grep-file > .row`, `.grep-hit`, `#proposalList .row`, `#gitList .row` (an added folder's rows are drawn there too), `.rv-item`, `#specsView .row`, `#steeringView .row`, `#traceList .row`, `.welcome .link`, `#sbContext`, `[data-spec-open]`; links: `a.loc`, `.msg.user .ref`, `.attached span`. Each match gets `tabindex="0"` and `role="button"` (`role="link"` for the links). One `keydown` listener turns Enter, and Space on a button, into `el.click()`. An element that already has a `tabindex` has keys of its own (the plan line, Progress markers) and is left alone, so it never acts twice. The folder dialog's rows are not here: Enter in that dialog already means "go into the selected folder", so they are the dialog's (task 4). |
| The observer | A `MutationObserver` on `document.body` that looks only at added nodes, skips records inside `.xterm` (the terminal redraws its rows many times a second), and decorates what was added once per frame. A streamed reply redraws its message on every word, so doing the work per mutation would be per word. Pending work is also flushed by a capturing `keydown` listener, so a key never lands on a row that isn't ready yet. |
| Focus across redraws | Most of these rows live in lists that redraw when a row is used (Review, Changes, Sessions, Specs), and the focused row goes with the old list, leaving focus on the page body. A `focusin` listener remembers the focused element and how to find it again: its id, or its `data-*` attributes and its parents' up to the nearest id (a Review row: whichever row is selected, so focus follows j and k). When the observer sees the remembered element gone and focus on the body, it focuses the same thing in the new list, or else the first row (never a button, where a second Enter would act on something you didn't aim at) of the same container. A `mousedown` forgets it: a click on something that can't take focus is where you put focus. Measured in Chromium: removing the focused element fires `focusout` first and leaves `document.activeElement` on the body; hiding it does not move focus at all (menus and dialogs give focus back themselves). |
| Buttons inside rows | A session row's Delete and the `@` and Undo buttons in rows are real buttons inside the row. Enter or Space on one is that button's: the listener acts only when the row itself is the event's target. They are shown on `:focus-within` as well as `:hover`, so Tab reaches them where they are. |
| `roving(container, opts)` | One Tab stop for a set: the current item has `tabindex="0"`, the rest `-1`; arrows, Home and End move; optional typeahead; `opts.onMove(el)`; re-applies after the container's children change, keeping focus on the item with the same key (`opts.key(el)`). |
| `treeKeys()` | `roving` on `#tree` plus Left and Right, Enter, Space, F2, Delete, ⌘C and Shift+F10 (1.1–1.5). |
| `menu(m, opener)` | Roles, first-item focus, keys, and focus back to the opener (3.1, 3.2). |
| `modal(el)` | Dialog role, focus in, Tab trap, focus back (3.3, 3.4). |
| `announce(text, now)` | Writes to one of two visually hidden live regions (5.1–5.3). |
| `regions()` | F6 and Shift+F6 (2.5). |

## The tree

`#tree` gets `role="tree"` and `aria-label="Files"`. Each `.row` gets `role="treeitem"`, `aria-level` from its
`--depth` + 1, `aria-expanded` for folders (from the caret's `open` class) and `aria-selected` for the active file's
row. The focused row is `state.picked`: moving with the arrows sets `state.picked` and `state.pickedDir`, exactly as a
click does now, so New File, F2 and Delete keep their target. Left and Right call the same expand and collapse the
click handler uses. `renderTree` ends with one call, `a11y.treeRendered()`, which re-decorates and, if the tree had
focus before the redraw, focuses the row whose path was focused. `treeFocused` (`app.js`, beside the File menu's wiring) is replaced by
`$("#tree").contains(document.activeElement)`; its two uses in the `keydown` handler move to `treeKeys`.

The outline on the picked row (`.tree .row.picked` in `app.css`) becomes the tree's focus ring: drawn while the tree
has focus (`.tree:focus-within .row.picked`), a faint fill otherwise. That ends the two selection styles the review
noted (an outline on the last-clicked row and a fill on the open file's).

## Tabs, panel tabs, activity bar

- `#editorTabs`: `role="tablist"`; `.tab`: `role="tab"`, `aria-selected`, `aria-controls="editor"`; `#editor`:
  `role="tabpanel"`. `roving` with Left and Right; moving activates (sets `state.active` and calls `renderEditor`).
  Delete calls `closeTab`. `renderTabs` writes `aria-label="Close ${title}"` on the close button (a one-attribute
  template change) and ends with `a11y.tabsRendered()`.
- `.panel-tabs`: the same roles on `[data-ptab]` and the panel bodies; `showPanelTab` is the activation.
- `#activitybar` buttons: `aria-pressed` true for the shown view while the sidebar is open. `setView` and the badge
  renderers call `a11y.viewChanged()`, which also sets each button's `aria-label` from its base name and badge:
  "Changes, 2 waiting for review", "Progress, 1 of 2 done". Badges get `aria-hidden="true"`.
- `#chatTitleBtn`: `aria-label="Switch session: ${title}"`, so it no longer shares the name "New session" with the
  plus button beside it.

## Menus and dialogs

- `showMenu` (`app.js`, under "copy paths & context menu") ends with `a11y.menu($("#ctxMenu"), document.activeElement)`: `role="menu"`, items
  `role="menuitem"` and `tabindex="-1"`, separators `role="separator"`. Escape and item activation restore focus to the
  opener; a mouse click elsewhere doesn't (focus goes where the click went). Buttons that open menus (`#fileMenuBtn`,
  `#terminalMenuBtn`, `#workspaceBtn`, `#helpBtn`, `#termMore`) get `aria-haspopup="menu"` and `aria-expanded`.
- The four overlays (`#palette`, `#dialog`, `#folderDialog`, `#reportDialog`) all toggle `hidden`. `a11y.js` observes
  that attribute: on show, `modal(el)` sets `role="dialog"`, `aria-modal="true"`, `aria-labelledby` (the title element;
  `aria-label` for the palette), remembers `document.activeElement`, moves focus in if the dialog's own code hasn't,
  and traps Tab; on hide it restores focus. `#folderDialog` gets Escape from anywhere inside it.
- 3.5: `confirmDialog` focuses `#dialogCancel` when the OK label is destructive (the same test it uses for the red
  style: delete, discard, overwrite). Enter then cancels; the confirming button takes one Tab or a click.
- `#mentionPop`: `role="listbox"`, options `role="option"` with ids, and `aria-activedescendant` on `#input` while it
  is open (4.4). `renderMentions` ends with `a11y.mentionsRendered()`.

## Message actions

`.msg-actions` is `display: none` until hover, so its buttons can't take focus. It becomes always rendered but
transparent (`opacity: 0; pointer-events: none`), shown on `.msg.user:hover` and `.msg.user:focus-within`. Its buttons
get `aria-label`s from their titles.

## The Review list in view

Since #126 the Review list stacks above the diff in a narrow editor and is short, and `renderReviewTab` draws it
afresh on every j, k or arrow, starting it at the top: the selected row could be out of view. `renderReviewTab`
scrolls the selected row into view (`block: "nearest"`), one line.

## Announcements

Two elements in `index.html`: `#srPolite` (`role="status"`) and `#srNow` (`role="alert"`), class `sr-only` (clipped,
1px). `toast(msg, isErr)` calls `announce(msg, isErr)`. `updateBusy` and the `approval_needed`, `error` and `done`
branches call `a11y.turnState(kind)`, which announces "codepilot is working" (once per turn), "codepilot needs your
approval: <command>", "codepilot stopped with an error" or "codepilot finished". The transcript gets no live region
(5.3).

## Regions

`index.html`: `aria-label`s on the landmarks ("Views", "Sidebar", "Editor", "Panel", "Chat", "Status"). F6 focuses, in
order and skipping hidden ones: the sidebar view's first Tab stop, the active editor tab, the panel's current tab, and
`#input`.

## Tests

`tests/e2e/test_keyboard_access_ui.py` (new), keyboard only (no `click` after `open_app`):
- Tab reaches the tree in one stop; Down, Right, Enter open `agent/core.py`; Left twice closes the folder; typing "re"
  lands on README.md; F2 renames; a file created on disk redraws the tree and focus stays (1.x).
- three tabs: Right shows the next, Delete closes it, the close button's name (2.1, 2.2); panel tabs; `aria-pressed`
  and the Changes button's name with a pending change (2.3, 2.4); F6 goes sidebar → editor → chat (2.5).
- File menu: opens with focus on "New File…", Down, Escape returns focus to `#fileMenuBtn`; Shift+F10 on a tree row
  opens its menu (3.1, 3.2, 1.4).
- the folder dialog: focus inside, 30 Tabs never leave it, Escape returns focus to the opener; a Discard confirmation
  has focus on Cancel (3.3–3.5).
- Enter on a search hit, a session row, a `path:line` link; Tab reaches a message's Retry (4.1–4.3).
- the audit (4.5): on the welcome page, a file open, Changes, Search with hits, a chat with steps and a change,
  Review, Sessions and Steering, no visible element that looks clickable (`cursor: pointer`, or `grab`: tree rows can
  be dragged, and the review missed them for that reason) lacks a focusable self or ancestor. A `<label>` around a
  switch or checkbox passes: its control is inside it. What it finds is listed by tag, id, classes, `data-*` names and
  container, so a failure names the element. It found three things the spec hadn't listed: the tree's rows, the editor
  tabs and the code view's line numbers (`#gutter`, which selects lines on click). Each is allowed by name until the
  task that fixes it, and that task starts by removing its line: the tree and the line numbers in task 2 (the gutter
  becomes one Tab stop: Up and Down move, Enter or Space selects, Shift extends), the tabs in task 3.
- a focused row's ring is the accent, 2px, and has 3:1 against the row's fill composited over what's beneath, on a
  selected row and a plain one, in both themes (the contrast test from #122 checks text tokens, not rings).
- `#srPolite` and `#srNow` text after a turn ends, an approval is asked, and a toast (5.1, 5.2); `#transcript` has no
  `aria-live` (5.3).

Existing tests that confirm a destructive dialog with Enter must click `#dialogOk` instead (3.5); `confirm()` in
`test_files_ui.py` already clicks.
