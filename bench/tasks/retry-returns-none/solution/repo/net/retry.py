import time


class TransientError(Exception):
    """An error worth retrying (timeouts, 503s)."""


def call_with_retry(fn, attempts=3, delay=0.5, sleep=time.sleep):
    """Call fn(), retrying TransientError with exponential backoff."""
    for i in range(attempts):
        try:
            return fn()
        except TransientError:
            if i == attempts - 1:
                raise
            sleep(delay * 2 ** i)
