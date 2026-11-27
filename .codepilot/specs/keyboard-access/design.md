# Design

## One module: `static/a11y.js` (new, loaded after `app.js`)

The app redraws by replacing `innerHTML`, so roles and tab stops written into each template would touch every render
function in `app.js`. Instead `a11y.js` decorates what was rendered, keyed by selectors, and owns all the key handling.
Adding a new kind of row is adding a selector.

| Part | What it does |
|---|---|
| `ACTIVATABLE` | Selectors for click-only elements (`A11Y_BUTTONS`, `A11Y_LINKS`): `.session`, `.grep-file > .row`, `.grep-hit`, `#proposalList .row`, `#gitList .row` (an added folder's rows are drawn there too), `.rv-item`, `#specsView .row`, `#steeringView .row`, `#traceList .row`, `.welcome .link`, `#sbContext`, `[data-spec-open]`; links: `a.loc`, `.msg.user .ref`, `.attached span`. Each match gets `tabindex="0"` and `role="button"` (`role="link"` for the links). One `keydown` listener turns Enter, and Space on a button, into `el.click()`. An element that already has a `tabindex` has keys of its own (the plan line, Progress markers) and is left alone, so it never acts twice. The folder dialog's places (`#fdPlaces .row`) are added in task 4; its list of folders is not here: Enter in that dialog already means "go into the selected folder", so the list is the dialog's (see Menus and dialogs). |
| The observer | A `MutationObserver` on `document.body` that looks only at added nodes, skips records inside `.xterm` (the terminal redraws its rows many times a second), and decorates what was added once per frame. A streamed reply redraws its message on every word, so doing the work per mutation would be per word. Pending work is also flushed by a capturing `keydown` listener, so a key never lands on a row that isn't ready yet. |
| Focus across redraws | Most of these rows live in lists that redraw when a row is used (Review, Changes, Sessions, Specs), and the focused row goes with the old list, leaving focus on the page body. A `focusin` listener remembers the focused element and how to find it again: its id, or its `data-*` attributes and its parents' up to the nearest id (a Review row: whichever row is selected, so focus follows j and k). When the observer sees the remembered element gone and focus on the body, it focuses the same thing in the new list, or else the first row (never a button, where a second Enter would act on something you didn't aim at) of the same container. A `mousedown` forgets it: a click on something that can't take focus is where you put focus. Measured in Chromium: removing the focused element fires `focusout` first and leaves `document.activeElement` on the body; hiding it does not move focus at all (menus and dialogs give focus back themselves). |
| Buttons inside rows | A session row's Delete and the `@` and Undo buttons in rows are real buttons inside the row. Enter or Space on one is that button's: the listener acts only when the row itself is the event's target. They are shown on `:focus-within` as well as `:hover`, so Tab reaches them where they are. |
| The tree | One Tab stop with arrows, Home, End, typing, Left and Right, Enter, Space, F2, Delete, ⌘C and Shift+F10 (1.1–1.5); see The tree. |
| Tab strips | The editor's and the panel's tabs: one Tab stop each, arrows move and show, Delete closes (2.1–2.3). |
| `viewChanged()` | The activity bar's pressed state and the Changes count in its name (2.3, 2.4). |
| `menu(m)` | Roles, first-item focus, keys, and focus back to the opener (3.1, 3.2). |
| Dialogs | Dialog role and name, focus in, Tab kept inside, Escape, focus back to the opener (3.3–3.5). |
| `announce(text, now)` | Writes to one of two visually hidden live regions (5.1–5.3). |
| F6 | The next and previous pane, those shown (2.5). |

## The tree

`#tree` gets `role="tree"`, `aria-label="Files"` and `tabindex="-1"` (a click on empty space focuses it, and the keys
then act on the picked row, as `treeFocused` allowed). Each row (`[data-file]`, `[data-dir]`, and a session folder's
`.row.root`) gets `role="treeitem"`, `aria-level` from its `--depth` + 1, `aria-expanded` for folders (from the
caret's `open` class) and `aria-selected` for the picked row (selection follows focus in a tree; the open file's row
keeps its `on` fill). The `@` button in each row gets `tabindex="-1"`, so the tree stays one Tab stop; Add to chat is
in the row's menu.

The focused row is `state.picked`: moving with the keys sets `state.picked`, `state.pickedDir` and the `picked` class,
exactly as a click does, so New File, F2 and Delete keep their target. A redraw only moves the tab stop (to the picked
row, else the open file's, else the first): it never picks a row, which would silently change where New File creates
things. Right, Left, Enter and Space go through the row's own click, so expanding works the same for a folder and for
one of the session's folders (`folders.js`). Typing finds the next row whose name starts with what was typed in the
last 700 ms. Shift+F10 and the menu key dispatch a `contextmenu` event at the row, so the existing menu code opens the
same menu a right-click does.

`renderTree` ends with one call, `a11y.treeRendered()` (roles, the tab stop). Focus stays on the same path through a
redraw by the general rule (Focus across redraws), which `treeRendered` runs at once rather than waiting for the
observer. `treeFocused` and its `mousedown` listener are removed, and so are the global handler's F2, Delete and ⌘C
branches: the tree's own `keydown` handles them on the focused row. A click on a row now focuses it (rows have a
`tabindex`), which is what keeps F2 and Delete working after a click.

**⌘C.** The global branch copied the picked path whenever nothing was selected and focus wasn't in a text field,
wherever focus was (the editor, a button, the page). Requirement 1.4 ties it to the focused row, so it now works only
in the tree. Elsewhere ⌘C with nothing selected does nothing, as in any other app.

The outline on the picked row (`.tree .row.picked` in `app.css`) is drawn only while the tree has focus
(`.tree:focus-within .row.picked`; 2px when the keyboard put it there), a faint fill otherwise. That ends the two
selection styles the review noted (an outline on the last-clicked row and a fill on the open file's).

## Review's keys stay in the Review

`reviewKeys` acted on j, k, a, r and the arrows anywhere outside a text box while the Review tab was active, and a and
r apply and reject a change. With focus on a tree row, typing to find "a…" would have applied one, and Down would have
moved the Review list. It now acts only when the key's target is inside `.review` or is the page body (after a click on
the diff, which can't take focus): never in the tree, a tab strip, a menu or a dialog. One condition in `reviewKeys`.

## The code view's line numbers

The audit found `#gutter`'s numbers, which select lines on click (Shift extends), with no keyboard way. The gutter
becomes one Tab stop, a `listbox` whose current line is its `aria-activedescendant` (so a 3,000-line file doesn't get
3,000 tab stops): Up, Down, Page Up, Page Down, Home and End move and scroll it into view; Enter or Space selects the
line by dispatching the same click, with Shift to extend. The line you were on is kept per tab through the redraw a
selection causes. `a11y.js` decorates the gutter when it's drawn; `renderFileTab` is unchanged.

## Tabs, panel tabs, activity bar

- `#editorTabs`: `role="tablist"` (`aria-label="Open files"`); `.tab`: `role="tab"`, `aria-selected`,
  `aria-controls="editor"`, `tabindex` 0 on the shown tab and -1 on the rest; `#editor`: `role="tabpanel"`. Left,
  Right, Home and End move and activate (set `state.active`, call `renderEditor`, then focus the new tab: the redraw
  replaces the strip). Delete calls `closeTab`; focus then lands on the tab shown next (the redraw rule prefers a
  list's own tab stop when the focused tab is gone). Close buttons are `tabindex="-1"` (Delete does it) and named
  "Close <title>" in `renderTabs`'s template. `renderTabs` ends with `a11y.tabsRendered()`.
- **A click on a tab doesn't take focus.** Before, a click on a tab (a `div`) left focus on the page, and Review's
  j and k worked after clicking its tab. A tab with a `tabindex` would keep focus after a click, and Review's keys
  don't act from a tab strip. So a left mousedown on a tab is prevented and the focused element blurred: exactly the
  old behaviour, with focus on a tab only from the keyboard.
- **Reopening tabs on load (#125) doesn't move focus:** `tabsRendered` only moves focus when the strip had it and the
  redraw took it away.
- `.panel-tabs` holds the three tabs and the Clear and Close buttons, which can't be inside a tablist. The tabs get
  their own `<div class="ptabs" role="tablist" aria-label="Panel">` in `index.html`, each tab an id and
  `aria-controls`, each body `role="tabpanel"` and `aria-labelledby`. `.panel-tabs > button` rules in `app.css` move to
  `.ptabs > button`, and one layout test's selector follows. `showPanelTab` ends with `a11y.panelTabsShown()`
  (`aria-selected`, the tab stop); Left and Right call `showPanelTab`.
- `#activitybar` buttons: `aria-pressed` true for the view shown. Shown means the sidebar is shown, which since #126
  is `layoutShown(ide, "sidebar")` in `layout.js` (it also steps aside for room as `auto-no-sidebar`), not a check of
  `no-sidebar`. `setView` and `renderProposalList` call `a11y.viewChanged()`, and an observer on `#ide`'s class calls
  it when the sidebar is hidden or shown by any route. The Changes button's name carries its count ("Changes, 2
  waiting for review"). Progress already names its own (`progress.js`, since #101), so `progress.js` is untouched.
  Badges get `aria-hidden="true"` in `index.html`.
- `#chatTitleBtn`: `aria-label="Switch session: <title>"`, so it no longer shares the name "New session" with the
  plus button beside it. Three places in `app.js` write the title, so `a11y.js` watches `#chatTitle` instead of adding
  three calls.
- `app.js` calls `window.a11y?.…`, as `updateBusy` calls `window.renderPinnedPlan?.()`: `a11y.js` loads last, and
  code after an `await` in `init` can draw before it has run. On load it catches up (tabs, tree, panel tabs, views).

## Menus and dialogs

- `showMenu` (`app.js`, under "copy paths & context menu") ends with `a11y.menu($("#ctxMenu"))`: `role="menu"`, items
  `role="menuitem"` and `tabindex="-1"`, separators `role="separator"`, focus on the first item. Up and Down go round
  the ends; Home, End and a letter move; Enter or Space runs an item; Escape or Tab closes. The opener isn't
  `document.activeElement` at that moment (a right-click may not have focused anything): it's the last element focused
  outside any overlay (menu, dialog, the session switcher), tracked by the `focusin` listener. When the menu hides, an
  observer on its `hidden` gives focus back to the opener, or the same thing redrawn, if focus is still in the menu or
  on the body; an item that put focus somewhere itself (a dialog) keeps it, and a click elsewhere puts focus where it
  went. (Hiding doesn't move focus in Chromium, so this must be done; see task 1's measurement.) Buttons that open
  menus get `aria-haspopup="menu"` and `aria-expanded` in `index.html`: `#workspaceBtn`, `#fileMenuBtn`,
  `#terminalMenuBtn`, `#helpBtn`, `#termMore` and `#newSteeringBtn`.
- The four overlays (`#palette`, `#dialog`, `#folderDialog`, `#reportDialog`) all toggle `hidden`. Each gets
  `role="dialog"`, `aria-modal="true"` and `aria-labelledby` its title (`#dialogTitle`; the folder and report dialogs'
  headings get ids, `fdTitle` and `rpHeading`, in `index.html`) or, for the palette, `aria-label="Go to file"`.
  `a11y.js` observes `hidden`. On show it remembers the opener and moves focus in (to its text box, else its first
  control) if the dialog's own code hasn't; Tab and Shift+Tab go round inside it, and Escape closes it from anywhere
  inside (it clicks the dialog's Cancel or close button; before, a prompt closed on Escape only from its text box).
  On hide it gives focus back, after the key that closed it has been handled (a zero-delay timeout): done within that
  key's handling, Enter in a prompt's text box went on to click the button the focus had just returned to (New Folder)
  and opened the prompt again. Found by `test_files_ui.py` and the spec tests, which answer prompts with Enter.
- **The opener is not `document.activeElement` on show.** `promptDialog` and `confirmDialog` focus their input or
  button before the observer sees the dialog shown, so reading `document.activeElement` there finds the dialog itself
  and the opener is lost. The opener is the last element focused outside any overlay, which the `focusin` listener
  keeps (menus use the same). A dialog opened from a menu item (Rename… on a row) gives focus back to what opened the
  menu. Focus goes back only if it's still in the dialog or on the body: the observer runs before the code awaiting
  the dialog continues, so an action that then moves focus (opening a file) wins.
- `#folderDialog` already closed on Escape from anywhere inside (its own `keydown`), so `app.js` needs nothing for
  that. Its list is a listbox, one tab stop, Up, Down, Home and End move, and the row you're on is selected as a click
  selects it, so Enter (the dialog's own key) goes into it; its places are buttons. The dialog's `keydown` lets Enter
  on a place through to the place (one condition in `app.js`). These were in the click-only list in the first draft,
  where Enter would have both selected a row and closed the dialog on the folder shown.
- 3.5: `confirmDialog` focuses `#dialogCancel` when the OK button is red (`danger`: delete, discard, overwrite). Enter
  then cancels; the confirming button takes one Tab or a click. No browser test confirmed one of these with Enter: they
  click `#dialogOk` (`confirm()` in `test_files_ui.py`) or confirm a prompt by Enter in its text box, which is unchanged.
- `#mentionPop` follows the session switcher (`sessions.js`, #100): `role="listbox"`, options `role="option"` with ids
  and `aria-selected`, and the current option as `aria-activedescendant` on `#input` while it's open, with
  `aria-controls` and `aria-autocomplete="list"` (4.4). The switcher's search box is also `role="combobox"`; a
  `<textarea>` can't take that role, so the message box stays a text box with an active descendant. Three functions
  draw the list (`renderMentions`, `showSkillMenu`, `showSteeringMenu`), so `a11y.js` observes `#mentionPop` instead
  of adding a call to each.

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
order and skipping hidden ones: the sidebar view's first Tab stop, the active editor tab (the editor's first control
with no tabs), the panel's current tab, and `#input`. Hidden is asked the way the layout knows it: the sidebar and chat
through `layoutShown`, the panel by `no-panel`. Shift+F6 goes the other way; from outside the four (the title bar,
the activity bar) F6 goes to the first and Shift+F6 to the last.

No tooltip gains a shortcut here. Any that do later are written through `keyLabel` in `keys.js` (#123).

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
