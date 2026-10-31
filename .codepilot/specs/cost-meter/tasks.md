# Tasks: cost meter

- [x] 1. Move pricing into its own module
  - Test first: `tests/test_pricing.py` for `load`, `price_for`, `cost` (cache, local, unpriced) and `summarise`; the
    existing bench cost tests stay green.
  - `codepilot/pricing.py`; `bench.summarize` uses it; delete `bench._price_for`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
- [x] 2. Cost in the API and the usage events
  - Tests: `/usage` adds `cost`, `today`, `budget`, `prices_path`; `usage_since` across sessions; `turn-costs`
    assignment, including archived turns; the `usage` event has `cost`; explore usage counts.
  - `Store.usage_since`, `Store.usage_rows`; the server fields; the agent event; `CODEPILOT_PRICES` in config.
  - _Requirements: 2.2, 2.4, 2.5, 3.1_
- [x] 3. Status bar, Memory and Activity
  - E2E first, with a prices file: `· $` in the status bar; the tooltip shows the model breakdown and today; Memory
    shows $ per row and the today line; no prices shows the hint; Activity rows show $.
  - `static/cost.js`; hooks in `renderUsage`, `renderMemory` and the `usage` case in `render()`.
  - _Requirements: 1.5, 2.1, 2.2, 2.3, 2.4_
- [x] 4. Estimate before Run all remaining
  - E2E: after one scripted task, Run all asks with an estimate; with none, it runs straight away.
  - `estimateRunAll` in `static/cost.js`; the `#spAll` handler calls it.
  - _Requirements: 3.1, 3.2_
- [x] 5. Daily cap
  - Tests: `test_spend.py` (warn, stop, override, date rollover); an agent turn stops before the next model call;
    unpriced usage excluded and named.
  - `codepilot/spend.py`; checks in `_loop_steps` and `_explore`; the `budget` event; `POST /api/budget/override`;
    `CODEPILOT_DAILY_BUDGET`.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
- [x] 6. Budget banner
  - E2E: the banner appears and Continue anyway lifts the cap.
  - `case "budget"` in `render()`, using `static/cost.js`.
  - _Requirements: 4.3_
- [x] 7. Docs
  - `docs/usage.md` (Model tiers and cost), `docs/configuration.md`, `docs/benchmark.md` (one prices file for both).
  - _Requirements: 1.1, 1.5_
