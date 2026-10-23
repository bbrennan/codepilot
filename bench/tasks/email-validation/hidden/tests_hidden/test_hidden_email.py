import pytest

from accounts.validate import is_valid_email


@pytest.mark.parametrize("ok", ["a@b.co", "first.last@example.com", "x_y-z@mail.example.co.uk", "u+1@d.io"])
def test_valid(ok):
    assert is_valid_email(ok)


@pytest.mark.parametrize("bad", ["a@b", " a@b.co", "a@b.co ", "@example.com", "user@@example.com",
                                 "user@exa mple.com", "user@example", "user@.com", "a@b.co\n", ""])
def test_invalid(bad):
    assert not is_valid_email(bad)
