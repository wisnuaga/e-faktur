import re
from typing import Optional


def normalize_number(value: str) -> Optional[str]:
    if value is None:
        return None
    # Remove all non-digit chars
    digits = re.sub(r"\D", "", value)
    return digits or None
