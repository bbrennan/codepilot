import re

EMAIL = re.compile(r"[^@]+@[^@]+")


def is_valid_email(address):
    return bool(EMAIL.match(address))
