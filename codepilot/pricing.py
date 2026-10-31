"""Turning tokens into dollars, for the app and the benchmark alike.

Prices are per million tokens, in a TOML file you keep (bench/prices.example.toml shows the format): they change, and
Bedrock's differ by region, so none are built in. A model with no price is "unpriced", never $0: a total that quietly
leaves out a model would read as cheaper than it is, so callers say which ones are missing.
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

KINDS = ("input", "output", "cache_read", "cache_write")


def load(path: Path) -> dict:
    """{} if there's no file. Raises ValueError, naming the file, if it can't be read."""
    name = Path(path).name
    try:
        prices = tomllib.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise ValueError(f"{name}: {exc}") from None
    for model, rates in prices.items():
        if not isinstance(rates, dict):
            raise ValueError(f"{name}: {model} should be a table of prices")
        for kind in KINDS:
            if kind in rates and not _is_rate(rates[kind]):
                raise ValueError(f"{name}: {model}.{kind} should be a number, zero or more")
    return prices


def _is_rate(value: object) -> bool:
    # bool is an int to Python, and nan or inf would pass a sum then break the JSON that carries it.
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def price_for(model: str, prices: dict | None) -> dict | None:
    """The first key the model id contains: ids carry prefixes and suffixes (us.anthropic.…-v1:0)."""
    for key, value in (prices or {}).items():
        if key in model:
            return value
    return None


def cost(row: dict, prices: dict | None, local: bool = False) -> float | None:
    """Dollars for a row of token counts (its model, and input, output, cache_read, cache_write). None: no price.

    A row says itself whether a local model served it: the provider today says nothing about last week's calls.
    """
    if local or row.get("local"):
        return 0.0
    price = price_for(row["model"], prices)
    if price is None:
        return None
    return sum((row.get(kind) or 0) * price.get(kind, 0) for kind in KINDS) / 1e6


def summarise(rows: list[dict], prices: dict | None, local: bool = False) -> dict:
    """{total, unpriced: [models], by_model: rows plus their cost}. The total covers priced models only."""
    by_model = [{**row, "cost": cost(row, prices, local)} for row in rows]
    return {"total": sum(r["cost"] or 0 for r in by_model),
            "unpriced": list(dict.fromkeys(r["model"] for r in by_model if r["cost"] is None)), "by_model": by_model}
