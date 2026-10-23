from datetime import datetime, timedelta, timezone

from auth.tokens import is_expired

UTC = timezone.utc


def test_aware_inputs():
    assert not is_expired("2999-01-01T00:00:00+00:00")
    assert is_expired("2000-01-01T00:00:00Z")


def test_offsets_are_respected():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    assert is_expired("2024-01-01T13:00:00+02:00", now=now)       # 11:00 UTC
    assert not is_expired("2024-01-01T13:00:00+00:00", now=now)


def test_naive_now_is_utc():
    assert not is_expired("2024-01-01T12:30:00+00:00", now=datetime(2024, 1, 1, 12, 0))
    assert is_expired("2024-01-01T11:30:00", now=datetime(2024, 1, 1, 12, 0, tzinfo=UTC))


def test_default_now():
    soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert not is_expired(soon)
