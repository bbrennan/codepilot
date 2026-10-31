# Design: cost meter

## Overview

The `usage` table already records each model call: session, model, input, output, cache read and cache write tokens,
and time. Cost is those numbers multiplied by prices from a TOML file. The only new state is the daily-cap override.

## Architecture

```
usage rows (store.py) ──► pricing.cost_rows(rows, prices) ──► /usage JSON (+ $) ──► status bar, Memory, Activity
                                    │
Agent._loop_steps (before each model call) ──► budget.check(today_cost) ──► notice / {"type":"budget"} + stop
```

### New: `codepilot/pricing.py`

Its one reason to change is turning tokens into dollars.

```python
def load(path: Path) -> dict                     # {} if missing; ValueError with the line on bad TOML (shown once)
def price_for(model: str, prices: dict) -> dict | None   # moved from bench._price_for (1.2)
def cost(model: str, row: dict, prices: dict, local: bool) -> float | None  # None = unpriced (1.4)
def summarise(rows: list[dict], prices: dict, is_local) -> dict
    # {"total": float, "unpriced": [models], "by_model": [{..., "cost": float|None}]}
```

- **`bench.py`:** `summarize` calls `pricing.price_for` and `pricing.cost`, and `_price_for` is deleted. This is a
  pure move, so the existing benchmark tests guard it (1.2).
- **Local models:** the agent knows the provider. `is_local` is simply `cfg.provider == "ollama"` (1.3). Matching on
  the model id was rejected: Ollama's `name:tag` form collides with Bedrock ids such as `…-v1:0`.

### New: `codepilot/spend.py`

Its one reason to change is what has been spent. It joins the prices file, the store and today's date, so the session
view, per-turn costs and the daily cap live together rather than in two modules. The clock can be injected.

```python
class Spend:
    def __init__(self, cfg, store, today=datetime.now)
    def view(self, sid) -> dict         # by_model (with cost), cost, today, budget, prices {path, loaded, error}
    def record(self, sid, model, usage) -> None
    def call(self, model, usage) -> float | None
    def turns(self, sid) -> list[dict]  # [{mid, text, cost}]; cost None if it made no calls or part has no price
    def check(self) -> str              # ok | warn (first time past 80% today) | stop
    def capped(self) -> bool            # as check, but asking uses up no warning
    def spent_today(self) -> float
    def unpriced_today(self) -> list[str]
    def override_today(self) -> None
```

Prices are read from the file on each use, so editing it takes effect without a restart. Nothing is cached: one query
next to a model call costs nothing, and a stale total could let a tight cap overshoot.

### Changes to existing modules (wiring)

- **`store.py`:**
  - `usage(sid)` keeps its shape.
  - New `usage_since(ts) -> list[dict]` groups by model across sessions, for today (2.2).
  - New `usage_rows(sid) -> list[dict]` returns per-call rows with `created`, for turn costs (3.1).
- **`server.py`:**
  - `/api/sessions/{sid}/usage` adds `cost` (a `summarise` of the session), `today` (`summarise` of `usage_since(local
    midnight)`), `budget` (the limit and whether it's overridden) and `prices_path`.
  - New `GET /api/sessions/{sid}/turn-costs` returns `[{"mid", "text", "cost"}]`. Usage rows are assigned to the turn
    whose start message (`is_user_turn`, including archived ones) precedes them.
  - New `POST /api/budget/override` (4.3).
- **`agent.py`:**
  - The `usage` event gains `"cost"` (for that call, using the prices loaded at session start) (2.4).
  - Before `self.llm.stream` in `_loop_steps`, and in `_explore`, it calls `self.budget.check(today_cost())`.
    - On `warn` it yields a `notice` (4.2).
    - On `stop` it yields `{"type": "budget", "spent": x, "limit": y}`, then `done`, and returns. That ends the turn
      cleanly, like the step limit (4.3).
- **`config.py`:** `prices_path` (`CODEPILOT_PRICES`, default `home/"prices.toml"`) and `daily_budget: float | None`
  (`CODEPILOT_DAILY_BUDGET`). Both go in `docs/configuration.md`.

### Front end: new `static/cost.js`

- **`fmtUsd(x)`** formats `$0.004`, `$0.31` and `$12.40`; `null` gives `$?`.
- **Status bar:** `renderUsage` (in `app.js`) calls `costText(u)` and sets `#sbTokens` to `23.7k tokens · $0.31`. The
  title tooltip shows the cost by model, "Today: $1.84 of $5.00" and the unpriced models (2.1, 2.2). With no prices,
  the text is unchanged (1.5).
- **Memory → Token usage:** each row gains `· $0.12`, and a footer line shows "Today $1.84 (all sessions)". When there
  is no prices file, the line reads "Add prices to see dollars: copy bench/prices.example.toml to
  ~/.codepilot/prices.toml." (1.5)
- **Activity:** the `usage` case appends `· $0.004` (2.4).
- **Run all remaining:** the `#spAll` handler calls `estimateRunAll(spec)`.
  - It fetches `turn-costs`, takes the turns whose text starts with `Implement task` and names this spec, and averages
    the last 5.
  - If it found any, it shows `confirmDialog("Run all remaining?", "About $1.80 for 6 tasks (average of the last 3
    tasks).", "Run all")`. Otherwise it runs without asking (3.1, 3.2).
- **Budget banner:** `render()` handles `case "budget"` with an error-style banner: "Daily budget reached: $5.02 of
  $5.00." It has a **Continue anyway today** button, which posts the override (4.3). It deliberately does not resend
  anything, so I say "continue" myself.

## Data models

`~/.codepilot/budget.json`: `{"date": "YYYY-MM-DD", "override": bool, "warned": bool}`. Any other date counts as a new
day. It's replaced atomically, and the warning and the override share a lock, so neither can undo the other.

`usage` gains two additive columns:

- `local`: stamped when the call is recorded. Pricing by today's provider would make last week's cloud spend free after
  a switch to Ollama, and earlier local calls look unpriced after switching back.
- `rewound`: set when a rewind deletes the turn. The cost stays in the session and daily totals because it was billed,
  but it leaves turn costs, since those rows' times would otherwise fall inside the turn before.

Every model call goes through `Spend.record`, including summaries and second opinions, which get their usage from an
`on_usage` callback on `complete()`. `Store.usage` no longer groups by model alone: it groups by model and `local`.

## At the cap

Each kind of model call stops differently, because each can be mid-way through something:

| Call | At the cap |
|---|---|
| The main loop | Stops the turn with a `budget` event, and checks again after a summary, which may be what reached it |
| `explore` | Returns "Stopped" to the turn, which reports the budget once at its next check |
| A second opinion | Quietly skipped: the loop stops at its next check anyway |
| Manual compaction | Shows the budget banner instead, which is how the cap can be lifted |
| Continue in new session | Refused with a 409: it needs a summary, and without one the session's work would be lost |

## Error handling

| Situation | Behaviour |
|---|---|
| Malformed prices TOML | Memory and the status bar tooltip say why. Nothing shows as priced |
| Model id matches no key | `$?`; excluded from totals; listed under "unpriced" (1.4, 4.4) |
| Clock passes midnight mid-turn | The next `check` sees a new date and resets `warned` and `override` |
| Budget file unwritable | The override lives in memory for the server's lifetime, with a toast saying it won't survive a restart |

## Testing strategy

- **`tests/test_pricing.py`:**
  - `load` with missing, valid and malformed files.
  - `price_for` matching.
  - `cost` with cache fields, local models and unpriced models.
  - `summarise` totals that exclude unpriced models (1.1, 1.3, 1.4).
- **`tests/test_bench.py`:** the existing cost tests still pass after the move (1.2).
- **`tests/test_budget.py`:** warn once at 80%, stop at 100%, the override lasts until the date changes, and an
  injected `today` (4.1–4.3).
- **`tests/test_agent.py`:**
  - The `usage` event carries `cost`.
  - With a tiny budget, a FakeLLM turn stops before the second model call with a `budget` event (4.3).
  - Explore calls count (2.5).
- **`tests/test_server.py`:** the `/usage` JSON fields, `turn-costs` assignment, and the override endpoint.
- **`tests/e2e/test_ui.py`**, with a prices file in the test home:
  - The status bar shows `· $`, and the tooltip shows today (2.1, 2.2).
  - Memory rows show $ (2.3).
  - "Run all remaining" after one task shows the estimate dialog (3.1).
  - The budget banner appears and Continue anyway works (4.3).

## Alternatives rejected

- **Shipping current prices in the app.** They change, and Bedrock prices differ by region. The example file stays an
  example, and I keep my own copy.
- **A per-session budget.** My bill is per day and per month, not per session. A daily cap matches how I'd think about
  a runaway run.
- **Blocking a turn up front from an estimate.** Estimates from a few tasks are rough. A confirmation informs; the cap
  enforces.
