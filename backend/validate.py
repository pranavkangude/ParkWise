"""Input validation helpers (Member 3). Every user-supplied value goes through one of these before it reaches SQL.

They turn wrong types and out-of-range values into a clear 400 instead of a crash (500) or a database error.
"""
from decimal import Decimal, InvalidOperation
from flask import request
from errors import ApiError


def json_body():
    """The request body as a dict. An empty body gives {}. A list, number or invalid JSON gives 400."""
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ApiError("Send a JSON object.")
    return data


def text(value, name, max_len, min_len=1):
    """Trimmed single-line text with a length limit."""
    if not isinstance(value, str):
        raise ApiError(f"'{name}' must be text.")
    v = value.strip()
    if len(v) < min_len:
        raise ApiError(f"'{name}' is required." if min_len else f"'{name}' is empty.")
    if len(v) > max_len:
        raise ApiError(f"'{name}' must be at most {max_len} characters.")
    if any(ord(c) < 32 for c in v):
        raise ApiError(f"'{name}' contains invalid characters.")
    return v


def opt_text(value, name, max_len):
    """Like text() but None or an empty string gives None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return text(value, name, max_len)


def secret(value, name, min_len, max_len):
    """A password: text that is NOT trimmed, with a length range."""
    if not isinstance(value, str):
        raise ApiError(f"'{name}' must be text.")
    if len(value) < min_len:
        raise ApiError(f"'{name}' must be at least {min_len} characters.")
    if len(value) > max_len:
        raise ApiError(f"'{name}' must be at most {max_len} characters.")
    return value


def number(value, name, lo, hi, places=2):
    """A decimal number within [lo, hi], rounded to `places` decimals. Returns a Decimal."""
    if isinstance(value, bool) or value is None or value == "":
        raise ApiError(f"'{name}' is required.")
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        raise ApiError(f"'{name}' must be a number.")
    if not d.is_finite():
        raise ApiError(f"'{name}' must be a number.")
    if d < Decimal(str(lo)) or d > Decimal(str(hi)):
        raise ApiError(f"'{name}' must be between {lo} and {hi}.")
    return d.quantize(Decimal(1).scaleb(-places))


def integer(value, name, lo, hi):
    """A whole number within [lo, hi]. 10.5 is refused (not rounded)."""
    d = number(value, name, lo, hi, places=6)
    if d != d.to_integral_value():
        raise ApiError(f"'{name}' must be a whole number.")
    return int(d)


def flag(value, name):
    """A true/false field. Accepts true/false/0/1 only; the string "false" is refused (it would be truthy)."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return int(value)
    raise ApiError(f"'{name}' must be true or false.")
