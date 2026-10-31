# Requirements: conventions-first `/init`

## Introduction

`/init` and **Generate foundation docs** draft `product.md`, `tech.md` and `structure.md`, which are always-on overviews
of the repo. The ETH Zurich AGENTS.md study (ICLR 2026) found that repository context files generally don't improve
task success and add more than 20% inference cost. Overviews in particular didn't help; only non-standard practices
were worth writing down. That study used only Python benchmarks, so it is suggestive, not conclusive. Even so, an
always-on doc costs tokens on every message, which is reason enough to keep it to what the agent can't infer.

This spec changes the default draft to a short `conventions.md` of non-obvious rules, keeps the Kiro foundation docs
available on request, and shows what always-on steering costs per message.

Out of scope: changing or deleting existing steering docs, and automatic trimming.

## 1. Draft conventions, not overviews

**User story:** As the developer, I want `/init` to write down only what CodePilot couldn't work out from the code, so
that every message doesn't pay for a summary it doesn't need.

1.1 WHEN I run `/init` or press **Draft conventions** in the Steering view THEN CodePilot SHALL investigate the repo and
propose one file, `.codepilot/steering/conventions.md` (`inclusion: always`), through `propose_edit`.
1.2 The draft SHALL contain only rules an agent couldn't infer from the code and its standard tooling: non-standard build
or test steps, forbidden patterns, project constraints, and gotchas. Each rule SHALL be one line naming the file or
command that shows it, and the draft SHALL be at most about 25 lines.
1.3 IF CodePilot finds nothing non-obvious THEN it SHALL say so and propose nothing.
1.4 IF `conventions.md` already exists THEN CodePilot SHALL propose additions to it rather than a replacement.
1.5 Existing steering docs SHALL NOT be changed.

## 2. Kiro foundation docs on request

**User story:** As the developer, I want the Kiro-style foundation docs still available, so that I can create them when I
use the repo with Kiro.

2.1 `/init foundation` and **Draft Kiro foundation docs** (in the Steering view's new-doc menu) SHALL run today's
foundation prompt unchanged.

## 3. Show what steering costs

**User story:** As the developer, I want to see how many tokens always-on steering adds to every message, so that I can
judge whether each doc earns its place.

3.1 The Steering view SHALL show the estimated tokens that always-on docs add to each message, in total and per doc.
3.2 The estimate SHALL use the same characters-per-token estimate the context meter uses, and SHALL be labelled as
approximate.
