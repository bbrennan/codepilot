"""What this has cost: per session, per turn and today, and the optional daily cap.

The 2026 backlash against metered tools was mostly about surprise, so cost is shown as it accrues, and a cap can stop a
runaway run. Usage in the store is the source of truth; prices are read from the file on each use, so editing it
takes effect without a restart.
"""

from __future__ import annotations

import json
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

    def _path(self) -> Path:
        return Path(self.cfg.prices_path) if self.cfg.prices_path else self.cfg.home / "prices.toml"

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
        return pricing.summarise(self.store.usage_since(self._midnight()), prices, self._local)

    def view(self, sid: str) -> dict:
        """What the status bar and Memory show. `by_model` is the session's usage, each with its cost."""
        prices, error = self._prices()
        session = pricing.summarise(self.store.usage(sid)["by_model"], prices, self._local)
        today = self._today_summary(prices)
        return {"by_model": session["by_model"],
                "cost": {"total": session["total"], "unpriced": session["unpriced"]},
                "today": {"total": today["total"], "unpriced": today["unpriced"]},
                "budget": {"limit": self.cfg.daily_budget, "overridden": bool(self._state().get("override"))},
                "prices": {"path": str(self._path()), "loaded": bool(prices), "error": error}}

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
            costs = [pricing.cost(r, prices, self._local) for r in rows if created <= r["created"] < until]
            turns.append({"mid": mid, "text": text, "cost": None if None in costs else round(sum(costs), 6)})
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
            self._state_path().write_text(json.dumps(state))
        except OSError:
            self._local_state = state  # holds for this server's lifetime

    def spent_today(self) -> float:
        return self._today_summary(self._prices()[0])["total"]

    def check(self) -> str:
        """Before a model call: ok, warn (first time past 80% today) or stop."""
        limit = self.cfg.daily_budget
        if limit is None:
            return "ok"
        spent = self.spent_today()
        state = self._state()
        if spent >= limit:
            return "ok" if state.get("override") else "stop"
        if spent >= limit * WARN_AT and not state.get("warned"):
            self._save({**state, "warned": True})
            return "warn"
        return "ok"

    def override_today(self) -> None:
        self._save({**self._state(), "override": True})
