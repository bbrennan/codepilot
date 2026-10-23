"""Auto: pick the model tier for each turn, by rules you can read, and say why.

Rules, first match wins:
  1. You ask for depth ("think hard", "ultrathink", "use opus", "be thorough")   -> hard
  2. The previous turn struggled (2+ failing test/command runs, or hit the step limit) -> hard
  3. Plan, Debug and Bug-hunt modes (reasoning-heavy)                            -> hard
  4. Ask mode with a short question                                               -> fast
  5. A big job: a long message, 3+ @files, or refactor/architecture/design/migrate -> hard
  6. Everything else                                                              -> main

Each tier means the newest model of its class the account can use (models.best_in_family): Haiku for
fast, Sonnet for main (the default), Opus for hard.

The model stays fixed within a turn. Switching mid-turn would throw away the prompt cache and the
model's own reasoning. When a turn keeps failing, the hard model is consulted once as an advisor instead
(see Agent._after_result), and the next turn starts on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEPTH = re.compile(r"\b(think (?:hard|harder|deeply|carefully)|ultrathink|use opus|be thorough|deep dive)\b", re.I)
BIG_JOB = re.compile(r"\b(refactor\w*|architect\w*|re-?design\w*|migrat\w*|rewrite|overhaul|from scratch)\b", re.I)
HARD_MODES = {"plan", "debug", "bughunt"}
LONG_MESSAGE = 1500
SHORT_QUESTION = 300


@dataclass
class Route:
    tier: str
    reason: str


def choose(mode: str, text: str, last_turn: dict | None = None) -> Route:
    last_turn = last_turn or {}
    if DEPTH.search(text):
        return Route("hard", "you asked for depth")
    if last_turn.get("failures", 0) >= 2:
        return Route("hard", f"the last turn hit {last_turn['failures']} failing runs")
    if last_turn.get("hit_limit"):
        return Route("hard", "the last turn ran out of steps")
    if mode in HARD_MODES:
        return Route("hard", f"{mode} mode needs careful reasoning")
    refs = len(re.findall(r"(?<![\w@`])@[\w.\-/~]+", text))
    if mode == "ask":
        return Route("fast", "a quick question") if len(text) <= SHORT_QUESTION and refs <= 1 else \
            Route("main", "a detailed question")
    if len(text) > LONG_MESSAGE or refs >= 3 or BIG_JOB.search(text):
        return Route("hard", "a large or structural change")
    return Route("main", "routine work")


def failed_run(name: str, output: str, is_error: bool) -> bool:
    """A test or command run that failed (the signal for escalating)."""
    if name not in ("run_tests", "run_command", "run_checks"):
        return False
    m = re.search(r"^exit code (-?\d+)", output, re.M)
    return is_error or bool(m and m.group(1) != "0")
