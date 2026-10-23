from datetime import datetime, timezone


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def is_expired(expires_at_iso, now=None):
    """True if the token's expiry time has passed."""
    expires = _utc(datetime.fromisoformat(expires_at_iso))
    now = _utc(now) if now is not None else datetime.now(timezone.utc)
    return now > expires
