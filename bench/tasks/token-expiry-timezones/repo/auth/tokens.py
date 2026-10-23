from datetime import datetime


def is_expired(expires_at_iso, now=None):
    """True if the token's expiry time has passed."""
    expires = datetime.fromisoformat(expires_at_iso)
    now = now or datetime.utcnow()
    return now > expires
