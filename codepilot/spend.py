"""What this has cost: per session, per turn and today, and the optional daily cap.

The 2026 backlash against metered tools was mostly about surprise, so cost is shown as it accrues, and a cap can stop a
runaway run. Usage in the store is the source of truth; prices are read from the file on each use, so editing it
takes effect without a restart.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import pricing
from .config import Config
from .store import Store

WARN_AT = 0.8


class Spend:
    def __init__(self, cfg: Config, store: Store, today: Callable[[], datetime] = datetime.now):
        self.cfg, self.store, self._now = cfg, store, today
        self._local_state: dict | None = None  # if the state file can't be written
        self._state_lock = threading.Lock()  # a warning on a session thread mustn't overwrite an override

    def _path(self) -> Path:
        return Path(self.cfg.prices_path).expanduser() if self.cfg.prices_path else self.cfg.home / "prices.toml"

    def _prices(self) -> tuple[dict, str]:
        try:
            return pricing.load(self._path()), ""
        except ValueError as exc:
            return {}, str(exc)

    @property
    def _local(self) -> bool:
        return self.cfg.provider == "ollama"

    def _midnight(self) -> float:
        return self._now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def _today_summary(self, prices: dict) -> dict:
        return pricing.summarise(self.store.usage_since(self._midnight()), prices)

    def view(self, sid: str) -> dict:
        """What the status bar and Memory show. `by_model` is the session's usage, each with its cost."""
        prices, error = self._prices()
        session = pricing.summarise(self.store.usage(sid)["by_model"], prices)
        today = self._today_summary(prices)
        return {"by_model": session["by_model"],
                "cost": {"total": session["total"], "unpriced": session["unpriced"]},
                "today": {"total": today["total"], "unpriced": today["unpriced"]},
                "budget": {"limit": self.cfg.daily_budget, "overridden": bool(self._state().get("override"))},
                "prices": {"path": str(self._path()), "loaded": bool(prices), "error": error}}

    def priced(self) -> bool:
        """Whether there are prices at all, which is what makes a missing one worth a $?."""
        return bool(self._prices()[0])

    def record(self, sid: str, model: str, usage: dict) -> None:
        """A model call has happened. It's stamped now, while the provider that served it is known."""
        self.store.add_usage(sid, model, usage, local=self._local)

    def call(self, model: str, usage: dict) -> float | None:
        """The cost of one model call, from the provider's usage block."""
        row = {"model": model, "input": usage.get("inputTokens", 0), "output": usage.get("outputTokens", 0),
               "cache_read": usage.get("cacheReadInputTokens", 0), "cache_write": usage.get("cacheWriteInputTokens", 0)}
        return pricing.cost(row, self._prices()[0], self._local)

    def turns(self, sid: str) -> list[dict]:
        """[{mid, text, cost}] per turn (for estimates). cost is None if part of the turn has no price."""
        prices = self._prices()[0]
        turns: list[dict] = []
        rows = self.store.usage_rows(sid)
        starts = self.store.turn_starts(sid)
        for i, (mid, created, text) in enumerate(starts):
            until = starts[i + 1][1] if i + 1 < len(starts) else float("inf")
            costs = [pricing.cost(r, prices) for r in rows if created <= r["created"] < until]
            # No calls isn't free: a task held at the cap would make an estimate look cheap.
            turns.append({"mid": mid, "text": text, "cost": None if not costs or None in costs else round(sum(costs), 6)})
        return turns

    # -- the daily cap ---------------------------------------------------------------------------------------------

    def _state_path(self) -> Path:
        return self.cfg.home / "budget.json"

    def _state(self) -> dict:
        """Today's {date, override, warned}. Any other date counts as a new day."""
        today = self._now().date().isoformat()
        state = self._local_state
        if state is None:
            try:
                state = json.loads(self._state_path().read_text())
            except (OSError, ValueError):
                state = {}
        return state if isinstance(state, dict) and state.get("date") == today else {"date": today}

    def _save(self, state: dict) -> None:
        self._local_state = None
        try:
            tmp = self._state_path().with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state))
            os.replace(tmp, self._state_path())  # the status bar reads this without the lock
        except OSError:
            self._local_state = state  # holds for this server's lifetime

    def spent_today(self) -> float:
        return self._today_summary(self._prices()[0])["total"]

    def unpriced_today(self) -> list[str]:
        return self._today_summary(self._prices()[0])["unpriced"]

    def capped(self) -> bool:
        """Is the cap in force? Unlike check, asking uses up no warning."""
        limit = self.cfg.daily_budget
        return limit is not None and self.spent_today() >= limit and not self._state().get("override")

    def check(self) -> str:
        """Before a model call: ok, warn (first time past 80% today) or stop."""
        limit = self.cfg.daily_budget
        if limit is None:
            return "ok"
        spent = self.spent_today()
        with self._state_lock:
            state = self._state()
            if spent >= limit:
                return "ok" if state.get("override") else "stop"
            if spent >= limit * WARN_AT and not state.get("warned"):
                self._save({**state, "warned": True})
                return "warn"
        return "ok"

    def override_today(self) -> None:
        with self._state_lock:
            self._save({**self._state(), "override": True})
