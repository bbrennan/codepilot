def line_total(price, qty, discount_pct=0):
    """Price x quantity minus a percentage discount, rounded to cents."""
    return round(price * qty * (1 - discount_pct / 100), 2)


def invoice_total(lines):
    """Sum of line totals. `lines` are dicts with price, qty and optional discount_pct."""
    return sum(line_total(**line) for line in lines)
