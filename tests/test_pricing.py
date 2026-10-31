"""Turning tokens into dollars, one way for the app and the benchmark."""

import pytest

from codepilot import pricing

PRICES = {"claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.2, "cache_write": 2.5},
          "claude-haiku-5-5": {"input": 0.1, "output": 0.5}}


def row(model="anthropic.claude-sonnet-5-5", **tokens):
    return {"model": model, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, **tokens}


def test_load_reads_the_benchmarks_format(tmp_path):
    f = tmp_path / "prices.toml"
    f.write_text('["claude-sonnet-5-5"]\ninput = 2.0\noutput = 10.0\n')
    assert pricing.load(f) == {"claude-sonnet-5-5": {"input": 2.0, "output": 10.0}}


def test_load_without_a_file_is_empty(tmp_path):
    assert pricing.load(tmp_path / "nope.toml") == {}


def test_load_explains_a_broken_file(tmp_path):
    f = tmp_path / "prices.toml"
    f.write_text("[oops\n")
    with pytest.raises(ValueError, match="prices.toml"):
        pricing.load(f)


def test_price_for_matches_keys_inside_the_model_id():
    assert pricing.price_for("us.anthropic.claude-sonnet-5-5-v1:0", PRICES)["input"] == 2.0
    assert pricing.price_for("gpt-9", PRICES) is None and pricing.price_for("x", None) is None


def test_cost_counts_every_kind_of_token():
    r = row(input=1_000_000, output=100_000, cache_read=1_000_000, cache_write=1_000_000)
    assert pricing.cost(r, PRICES) == pytest.approx(2.0 + 1.0 + 0.2 + 2.5)


def test_a_price_a_model_doesnt_list_counts_as_zero():
    assert pricing.cost(row("claude-haiku-5-5", input=1_000_000, cache_read=999), PRICES) == pytest.approx(0.1)


def test_local_models_cost_nothing_and_unknown_ones_have_no_cost():
    assert pricing.cost(row("llama3.2:3b", input=5), PRICES, local=True) == 0.0
    assert pricing.cost(row("gpt-9", input=5), PRICES) is None


def test_summarise_totals_priced_models_and_names_the_rest():
    rows = [row(input=1_000_000), row("gpt-9", input=9), row("claude-haiku-5-5", output=1_000_000)]
    s = pricing.summarise(rows, PRICES)
    assert s["total"] == pytest.approx(2.5) and s["unpriced"] == ["gpt-9"]
    assert [r["cost"] for r in s["by_model"]] == [pytest.approx(2.0), None, pytest.approx(0.5)]


def test_summarise_of_nothing():
    assert pricing.summarise([], PRICES) == {"total": 0.0, "unpriced": [], "by_model": []}


@pytest.mark.parametrize("text", ['rate = 2.0\n', '["m"]\ninput = "2.0"\n', '["m"]\ninput = nan\n',
                                  '["m"]\ninput = inf\n', '["m"]\ninput = -1.0\n', '["m"]\ninput = true\n'])
def test_load_refuses_prices_that_arent_prices(tmp_path, text):
    f = tmp_path / "prices.toml"
    f.write_text(text)
    with pytest.raises(ValueError, match="prices.toml"):
        pricing.load(f)


def test_a_row_remembers_it_was_local_whatever_the_current_provider():
    assert pricing.cost(row("gpt-9", input=5, local=1), PRICES) == 0.0
    assert pricing.cost(row(input=1_000_000, local=0), PRICES) == 2.0
