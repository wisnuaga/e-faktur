import io
import re
import pdfplumber
from typing import Optional, Dict
from app.core.normalizers import (
    normalize_number,
    normalize_npwp,
    normalize_faktur_number,
    normalize_date,
)

LABELS = {
    "npwpPenjual": [r"NPWP\s*Penjual", r"NPWP\s*PKP\s*Penjual"],
    "namaPenjual": [r"Nama\s*Penjual"],
    "npwpPembeli": [r"NPWP\s*Pembeli", r"NPWP\s*Lawan\s*Transaksi"],
    "namaPembeli": [r"Nama\s*Pembeli", r"Nama\s*Lawan\s*Transaksi"],
    "nomorFaktur": [r"Nomor\s*Faktur"],
    "tanggalFaktur": [r"Tanggal\s*Faktur"],
    "jumlahDpp": [r"Jumlah\s*DPP", r"DPP\s*Total"],
    "jumlahPpn": [r"Jumlah\s*PPN", r"PPN\s*Total"],
}

RE_NUMERIC = re.compile(r"([\d\.,]+)")
RE_NPWP = re.compile(r"\b\d{15}\b")
RE_FAKTUR_NUMBER = re.compile(r"\b\d{16}\b")
RE_DATE = re.compile(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b")


def _extract_text(file_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        text = []
        for p in pdf.pages:
            t = p.extract_text() or ""
            text.append(t)
        return "\n".join(text)

def _find_after_label(text: str, label_patterns, take_numeric=False) -> Optional[str]:
    for pat in label_patterns:
        m = re.search(pat + r".{0,50}", text, flags=re.IGNORECASE)
        if m:
            snippet = text[m.end(): m.end()+50]
            if take_numeric:
                nm = RE_NUMERIC.search(snippet)
                if nm:
                    return nm.group(1)
            else:
                # take next token/line
                nxt = snippet.strip().splitlines()[0] if snippet else ""
                return nxt.strip(": \t")
    return None


def extract_fields(file_bytes: bytes) -> Dict[str, Optional[str]]:
    text = _extract_text(file_bytes)

    data = {}

    # Try labeled extraction first
    data["npwpPenjual"] = normalize_npwp(_find_after_label(text, LABELS["npwpPenjual"], take_numeric=True))
    data["namaPenjual"] = (_find_after_label(text, LABELS["namaPenjual"]) or None)

    data["npwpPembeli"] = normalize_npwp(_find_after_label(text, LABELS["npwpPembeli"], take_numeric=True))
    data["namaPembeli"] = (_find_after_label(text, LABELS["namaPembeli"]) or None)

    data["nomorFaktur"] = normalize_faktur_number(_find_after_label(text, LABELS["nomorFaktur"], take_numeric=True))
    data["tanggalFaktur"] = normalize_faktur_number(_find_after_label(text, LABELS["tanggalFaktur"]))

    data["jumlahDpp"] = normalize_number(_find_after_label(text, LABELS["jumlahDpp"], take_numeric=True))
    data["jumlahPpn"] = normalize_number(_find_after_label(text, LABELS["jumlahPpn"], take_numeric=True))

    # Fallbacks using regex directly if labeled failed
    if not data["npwpPenjual"]:
        m = RE_NPWP.search(text)
        if m: data["npwpPenjual"] = m.group(0)
    if not data["npwpPembeli"]:
        ms = list(RE_NPWP.finditer(text))
        if len(ms) >= 2:
            data["npwpPembeli"] = ms[1].group(0)
    if not data["nomorFaktur"]:
        m = RE_FAKTUR_NUMBER.search(text)
        if m: data["nomorFaktur"] = m.group(0)
    if not data["tanggalFaktur"]:
        m = RE_DATE.search(text)
        if m: data["tanggalFaktur"] = normalize_date(m.group(0))

    return data

def extract_qr_url(file_bytes: bytes) -> Optional[str]:
    """Best-effort QR decode: rasterize 1st page and scan."""
    try:
        # Render first page to image using pdfplumber (based on vector text; low-res but ok for QR)
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if not pdf.pages:
                return None
            page = pdf.pages[0]
            # Use page.to_image().original which returns a PIL Image
            pil = page.to_image(resolution=200).original
            codes = qr_decode(pil)
            for c in codes:
                data = c.data.decode('utf-8', errors='ignore')
                # Simple URL check
                if data.startswith("http://") or data.startswith("https://"):
                    return data
    except Exception:
        return None
    return None
