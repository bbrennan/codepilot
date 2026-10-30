"""`codepilot models` says whose credentials it used when none of them can call Bedrock."""

from dataclasses import replace

from codepilot import cli, models


def fake_data(available):
    return {"models": [{"id": "anthropic.claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "available": available,
                        "reason": "is not authorized to perform: bedrock:InvokeModel",  # no identity in it: it must come from the new output
                        "api": "Messages API", "window": 1_000_000}],
            "tiers": {"main": {"model": "anthropic.claude-sonnet-5-5", "configured": "anthropic.claude-sonnet-5-5",
                               "fallback": False}}}


def run(cfg, monkeypatch, capsys, available, profile=None):
    cfg = replace(cfg, provider="bedrock", profile=profile)
    monkeypatch.setattr(models, "discover", lambda c, refresh=False: fake_data(available))
    monkeypatch.setattr(cli, "_caller_identity", lambda c: "arn:aws:iam::111122223333:user/someone")
    cli.print_models(cfg)
    return capsys.readouterr().out


def test_when_nothing_is_usable_it_names_the_identity_and_how_to_pick_another(cfg, monkeypatch, capsys):
    out = run(cfg, monkeypatch, capsys, available=False)
    assert out.count("arn:aws:iam::111122223333:user/someone") == 1  # printed once, by the new identity line
    assert "default credential chain" in out and "CODEPILOT_AWS_PROFILE" in out and ".env" in out
    assert "exported" in out and "echo $AWS_PROFILE" in out  # a shell variable beats .env


def test_a_set_profile_is_named_instead(cfg, monkeypatch, capsys):
    out = run(cfg, monkeypatch, capsys, available=False, profile="my-profile")
    assert "profile my-profile" in out and "default credential chain" not in out


def test_nothing_extra_is_printed_when_models_work(cfg, monkeypatch, capsys):
    assert "CODEPILOT_AWS_PROFILE" not in run(cfg, monkeypatch, capsys, available=True)


def test_the_unavailable_list_says_where_the_models_went_not_that_the_picker_hides_them(cfg, monkeypatch, capsys):
    """The picker lists unavailable models greyed out (with the reason), so the CLI must not claim it hides them."""
    out = run(cfg, monkeypatch, capsys, available=False)
    assert "hides" not in out and "greyed out" in out
