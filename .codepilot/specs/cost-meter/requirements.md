# Requirements: cost meter

## Introduction

CodePilot shows tokens, but my provider bills me in dollars. The benchmark already prices tokens
(`bench/prices.example.toml`, `--prices`), but the app doesn't. The 2026 backlash against metered pricing was mostly
about **surprise** (Copilot AI Credits, Claude Code quota drain). The cure is seeing cost as it accrues, and before a
long run.

This spec shows the dollar cost of my sessions and of today, gives an estimate before "Run all remaining", and adds
an optional daily cap.

Out of scope: fetching live prices (prices come from a file I maintain), provider billing APIs, and budgets per
session or per project.

## 1. Prices

**User story:** As the developer, I want CodePilot to price tokens the same way the benchmark does, so that I maintain
prices in one place.

1.1 The system SHALL read per-million-token prices from `CODEPILOT_PRICES`, defaulting to `~/.codepilot/prices.toml`,
in the benchmark's format (keys matched against model ids; `input`, `output`, optional `cache_read` and `cache_write`).
1.2 The benchmark and the app SHALL use the same pricing code.
1.3 Models served by Ollama SHALL cost $0 and show as "local".
1.4 IF a model has no price THEN its cost SHALL show as "$?", with a hint naming the model and the prices file, and SHALL
NOT count as $0 in any total.
1.5 IF no prices file exists THEN the app SHALL show tokens as today, and the Memory view SHALL explain how to add prices
(copy `bench/prices.example.toml`). IF the file can't be read THEN the Memory view and the status bar tooltip SHALL say why.

## 2. See the cost

**User story:** As the developer, I want to see what a session and today have cost, so that nothing surprises me.

2.1 The status bar SHALL show the session's cost next to its tokens (`23.7k tokens · $0.31`), updated after every model
call.
2.2 Hovering it SHALL show the cost by model, today's total across all sessions, and the daily budget if one is set.
2.3 The Memory view's Token usage SHALL show the cost per model and today's total.
2.4 Each model-call row in the Activity panel SHALL show its cost.
2.5 Costs SHALL include the `explore` sub-agent, memory summaries and second opinions (every row in `usage`).

## 3. Estimate before long runs

**User story:** As the developer, I want an estimate before "Run all remaining", so that I can decide whether to run it
now.

3.1 WHEN I press **Run all remaining** AND at least one task of this spec was implemented in this session THEN the system
SHALL show "About $X for N tasks (average of the last K tasks)" and ask for confirmation.
3.2 IF no task has run yet THEN the system SHALL say "no estimate yet" and run without asking.

## 4. Daily cap (optional)

**User story:** As the developer, I want an optional daily spending cap, so that a runaway run can't cost much.

4.1 WHERE `CODEPILOT_DAILY_BUDGET` is set (USD) THEN the system SHALL check today's priced cost (local midnight) before
each model call.
4.2 WHEN today's cost first passes 80% of the budget THEN the chat SHALL show a notice once that day.
4.3 WHEN today's cost reaches the budget THEN the system SHALL stop the turn before the next model call, say so, and
offer **Continue anyway today**, which lifts the cap until midnight.
4.4 Unpriced usage SHALL NOT count towards the cap, and the notice SHALL say when some usage is unpriced.
