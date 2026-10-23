from net.retry import call_with_retry


def test_success_first_try():
    assert call_with_retry(lambda: 42, sleep=lambda s: None) == 42
