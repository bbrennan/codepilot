---
name: plan-feature
description: Turn a feature request or larger change into an agreed, verifiable implementation plan before writing code. Use for new features, multi-file changes, migrations, or when requirements are fuzzy.
---
# Plan a feature

1. Restate the goal in one or two sentences and list what is unclear. Ask the few questions whose answers
   change the design (inputs/outputs, edge cases, compatibility, performance, rollout). One batch, not a
   drip; offer a sensible default for each.
2. Explore the code paths involved (`explore` for breadth, `read_file` for the core). Note existing
   patterns to reuse and anything that constrains the design.
3. Choose the approach. If there are real alternatives, give the trade-off in a few lines and recommend one.
4. Write the plan with `update_plan`, as small vertical steps that each leave the code working:
   - files and functions to change or add
   - tests to add per step (and the seam they use)
   - migrations, config, or docs to update
   - how each step is verified (which test or command)
5. Call out risks and what is out of scope. Then stop and let the user confirm or adjust before any edit.
   (In Plan mode this is all you do; the user switches to Build mode to carry it out.)
