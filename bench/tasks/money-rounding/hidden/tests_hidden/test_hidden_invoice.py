from decimal import Decimal

from billing.invoice import invoice_total, line_total


def test_lines():
    assert line_total("2.675", 1) == Decimal("2.68")
    assert line_total("19.99", 3) == Decimal("59.97")
    assert line_total("10.00", 1, discount_pct=15) == Decimal("8.50")
    assert line_total(Decimal("0.125"), 1) == Decimal("0.13")


def test_invoice_total_exact():
    lines = [{"price": "0.10", "qty": 1}, {"price": "0.20", "qty": 1}]
    total = invoice_total(lines)
    assert total == Decimal("0.30") and isinstance(total, Decimal)


def test_empty():
    assert invoice_total([]) == Decimal("0.00")
