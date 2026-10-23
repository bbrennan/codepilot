import pytest

from accounts.validate import is_valid_email


@pytest.mark.parametrize("ok", ["a@b.co", "user.name+tag@sub.example.org"])
def test_valid(ok):
    assert is_valid_email(ok)


@pytest.mark.parametrize("bad", ["a@b", "user@example.com ", "no-at-sign.com"])
def test_invalid(bad):
    assert not is_valid_email(bad)
