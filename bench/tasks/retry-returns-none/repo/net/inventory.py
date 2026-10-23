from .retry import TransientError, call_with_retry


def fetch_inventory(client):
    return call_with_retry(client.get_inventory)


__all__ = ["fetch_inventory", "TransientError"]
