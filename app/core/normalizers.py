import re
from typing import Optional
from datetime import datetime


def normalize_number(value: str) -> Optional[str]:
    if value is None:
        return None
    # Remove all non-digit chars
    digits = re.sub(r"\D", "", value)
    return digits or None

def normalize_company(name: str) -> str:
    raw = re.sub(r"\s+", " ", name).replace(".", " ").strip().upper()

    # match prefix CV atau PT
    m = re.match(r"^(CV|PT)[\s\.]*", raw)
    if m:
        prefix = m.group(1)
        cleaned = raw[m.end():].strip()
        return f"{prefix} {cleaned}"
    return raw

def normalize_idr(amount_str: str) -> float:
    """
    Convert Indonesian formatted amount like '36.364.855,00' to int (rupiah).
    """
    if not amount_str:
        return 0.0

    try:
        # Remove space
        amount_str = amount_str.strip()

        # Remove dot for thousands separation
        amount_str = amount_str.replace(".", "")

        # Replace comma with dot
        amount_str = amount_str.replace(",", ".")

        # Convert to float
        amount = float(amount_str)

        return amount
    except ValueError:
        return 0.0

def normalize_indonesian_date(date_str: str):
    # Mapping bulan Indo → angka
    months = {
        "januari": 1,
        "februari": 2,
        "maret": 3,
        "april": 4,
        "mei": 5,
        "juni": 6,
        "juli": 7,
        "agustus": 8,
        "september": 9,
        "oktober": 10,
        "november": 11,
        "desember": 12,
    }

    parts = date_str.strip().split()
    day = int(parts[0])
    month = months[parts[1].lower()]
    year = int(parts[2])

    return datetime(year, month, day).date()
