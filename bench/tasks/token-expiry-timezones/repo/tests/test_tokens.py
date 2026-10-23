from datetime import datetime

from auth.tokens import is_expired


def test_naive_past():
    assert is_expired("2000-01-01T00:00:00", now=datetime(2024, 1, 1))
