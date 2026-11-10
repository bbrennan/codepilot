# Design

## Where it lives

- `codepilot/static/progress.js` (new): the view. `#progressList` holds the cards; `placeTaskCard(card, at)` puts a
  card there (newest first) and a marker line at `at` in the chat (`card._marker`, `marker._card`);
  `refreshProgress()` redraws markers and the activity-bar badge from the live card; `showProgress(card)` opens the
  view at a card; the switch once per card (1.3) is `card._shown`, set when a card is placed live outside a replay.
  The empty state (1.4). Loaded after `taskcard.js`.
- `taskcard.js`, `plan.js`, `specrun.js`: cards are placed with `placeTaskCard` instead of in the chat, and looked up in
  both places (`CHAT_AND_PROGRESS`, `:is(#transcript, #progressList)`). A plan made inside a spec task still goes
  under that task (no marker). `unfileRewound` also removes a card whose marker was rewound away. `resetTaskCards`
  empties the view. `refreshTaskCard` calls `refreshProgress`.
- `app.js` (wiring): the chat's click handler is also the Progress list's (Open, Apply, Open spec, file links); lookups
  of filed content (`[data-prop]`, wait rows, verification cards) use `CHAT_AND_PROGRESS`; `render` passes `replay`
  so a reload doesn't switch the sidebar. `steps.js`, `verify.js` and `cost.js` lookups likewise.
- `index.html`: the activity-bar button with its badge, the view. `app.css`: the marker and the view.

## Decisions

- The cards move rather than being mirrored: one element, so the filing, rewind and replay logic stays as it is.
- Newest first, with ended cards folded below: the live run is at the top, its history a scroll away.
- The marker replaces the card where the plan was made, so the chat still says when a plan started and how it ended.

## Tests

E2E: a plan shows in Progress, not the chat, with its marker and badge; the sidebar switches once, not again after you
leave, not on reload; the marker and pinned line open the view at the card; Apply works on a change filed under a
step; Edit takes a later card away; another session has its own; the empty state. The existing plan and spec-run card
tests run against the view.
