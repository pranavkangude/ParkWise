import re
from datetime import datetime
from errors import ApiError

def parse_dt(value, name):
    """Accept 'YYYY-MM-DDTHH:MM' (browser) or 'YYYY-MM-DD HH:MM[:SS]'."""
    if not value:
        raise ApiError(f"'{name}' is required.")
    s = str(value).replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise ApiError(f"'{name}' must look like 2026-10-30 14:30.")

def to_int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(f"'{name}' must be a number.")

def norm_reg(value):
    return re.sub(r"\s+", "", str(value or "")).upper()
