---
name: handoff
description: Write a handoff so a fresh session (or a colleague) can pick up exactly where this one stopped. Run with /handoff.
disable-model-invocation: true
---
# Handoff

Summarise the current state of work for someone starting cold:

1. Goal: what we are trying to achieve and why.
2. Done: changes applied (proposal numbers and files), tests or commands run and their results.
3. Findings: root causes, evidence (`path:line`, trace files), decisions made and why.
4. Open: what is pending, next concrete steps in order, and known risks or unverified assumptions.
5. How to resume: the exact commands, files to open first, and any setup needed.

Keep it under ~300 words, as a Markdown block the user can paste. Then save the two or three facts that will
stay true beyond this task with `remember` (not the whole handoff).
