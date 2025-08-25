import re
from typing import Optional
from datetime import datetime


def normalize_number(value: str) -> Optional[str]:
    if value is None:
        return None
    # Remove all non-digit chars
    digits = re.sub(r"\D", "", value)
    return digits or None

def normalize_date(value: str) -> Optional[str]:
    if not value:
        return None
    # Accept 01/04/2022 or 01-04-2022
    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{4})", value.strip())
    if not m:
        return None
    d, mth, y = m.groups()
    try:
        dt = datetime(int(y), int(mth), int(d))
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return None

def normalize_npwp(value: str) -> Optional[str]:
    if not value:
        return None
    return normalize_number(value)

