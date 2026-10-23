---
name: grill
description: Interview the user about a design or idea until every important branch is decided. Run with /grill <topic>.
disable-model-invocation: true
---
# Grill me

The user wants their idea stress-tested before building it.

1. Read the relevant code first so questions are grounded in this codebase, not generic.
2. Ask 2-4 sharp questions at a time, most consequential first: requirements, edge cases, failure modes,
   data model, interfaces, migration, testing, operations, cost. For each, give your recommended answer so
   the user can just say "yes".
3. Push back on vague answers and on hidden assumptions. Point out contradictions with earlier answers or
   with the existing code.
4. Keep a running list of decisions and open questions with `update_plan`.
5. Stop when the open list is empty or the user says so. Finish with a crisp summary of the decisions,
   suitable for a spec or ticket, and offer to save the key facts with `remember`.
