"""Turning tokens into dollars, for the app and the benchmark alike.

Prices are per million tokens, in a TOML file you keep (bench/prices.example.toml shows the format): they change, and
Bedrock's differ by region, so none are built in. A model with no price is "unpriced", never $0: a total that quietly
leaves out a model would read as cheaper than it is, so callers say which ones are missing.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

KINDS = ("input", "output", "cache_read", "cache_write")


def load(path: Path) -> dict:
    """{} if there's no file. Raises ValueError, naming the file, if it can't be read."""
    try:
        return tomllib.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{Path(path).name}: {exc}") from None


def price_for(model: str, prices: dict | None) -> dict | None:
    """The first key the model id contains: ids carry prefixes and suffixes (us.anthropic.…-v1:0)."""
    for key, value in (prices or {}).items():
        if key in model:
            return value
    return None


def cost(row: dict, prices: dict | None, local: bool = False) -> float | None:
    """Dollars for a row of token counts (its model, and input, output, cache_read, cache_write). None: no price."""
    if local:
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
