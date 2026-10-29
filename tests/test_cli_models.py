"""`codepilot models` says whose credentials it used when none of them can call Bedrock."""

from dataclasses import replace

from codepilot import cli, models


def fake_data(available):
    return {"models": [{"id": "anthropic.claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "available": available,
                        "reason": "User: arn:aws:iam::111122223333:user/someone is not authorized to perform: bedrock:InvokeModel",
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
    assert "arn:aws:iam::111122223333:user/someone" in out
    assert "default credential chain" in out and "AWS_PROFILE" in out and ".env" in out


def test_a_set_profile_is_named_instead(cfg, monkeypatch, capsys):
    out = run(cfg, monkeypatch, capsys, available=False, profile="my-profile")
    assert "profile my-profile" in out and "default credential chain" not in out


def test_nothing_extra_is_printed_when_models_work(cfg, monkeypatch, capsys):
    assert "AWS_PROFILE" not in run(cfg, monkeypatch, capsys, available=True)
