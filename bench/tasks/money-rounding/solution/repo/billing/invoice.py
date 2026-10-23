from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def line_total(price, qty, discount_pct=0):
    """Price x quantity minus a percentage discount, rounded to cents."""
    raw = Decimal(str(price)) * Decimal(qty) * (Decimal(1) - Decimal(str(discount_pct)) / 100)
    return raw.quantize(CENT, rounding=ROUND_HALF_UP)


def invoice_total(lines):
    """Sum of line totals. `lines` are dicts with price, qty and optional discount_pct."""
    return sum((line_total(**line) for line in lines), Decimal("0.00")).quantize(CENT)
