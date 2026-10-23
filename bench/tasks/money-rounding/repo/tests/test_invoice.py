from decimal import Decimal

from billing.invoice import line_total


def test_half_up():
    assert line_total("2.675", 1) == Decimal("2.68")
