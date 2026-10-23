import pytest

from net.retry import TransientError, call_with_retry


def failing(n_failures, value="ok"):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] <= n_failures:
            raise TransientError("boom")
        return value
    return fn, calls


def test_raises_after_last_attempt():
    fn, calls = failing(10)
    sleeps = []
    with pytest.raises(TransientError):
        call_with_retry(fn, attempts=3, delay=1, sleep=sleeps.append)
    assert calls["n"] == 3
    assert sleeps == [1, 2]


def test_recovers():
    fn, calls = failing(1, "v")
    assert call_with_retry(fn, attempts=3, delay=0, sleep=lambda s: None) == "v"
    assert calls["n"] == 2


def test_non_transient_not_retried():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise KeyError("nope")
    with pytest.raises(KeyError):
        call_with_retry(fn, attempts=5, sleep=lambda s: None)
    assert calls["n"] == 1
