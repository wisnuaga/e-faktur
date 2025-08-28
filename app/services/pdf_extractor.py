import io
import re
import pdfplumber
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from typing import Optional, Dict, Union, Tuple, List
from datetime import datetime
from app.core.normalizers import (
    normalize_number,
    normalize_npwp,
    normalize_faktur_number,
    normalize_date,
)

LABELS = {
    "npwpPenjual": [r"NPWP\s*:", r"NPWP\s*Penjual", r"NPWP\s*PKP\s*Penjual"],
    "namaPenjual": [r"Nama\s*:", r"Nama\s*Penjual"],
    "npwpPembeli": [r"NPWP\s*:", r"NPWP\s*Pembeli", r"NPWP\s*Lawan\s*Transaksi"],
    "namaPembeli": [r"Nama\s*:", r"Nama\s*Pembeli", r"Nama\s*Lawan\s*Transaksi"],
    "nomorFaktur": [r"Kode dan Nomor Seri Faktur Pajak\s*[:]?\s*([0-9]{3}[.][0-9]{3}[-][0-9]{2}[.][0-9]{8})"],
    "tanggalFaktur": [r"JAKARTA SELATAN,\s*", r"Tanggal\s*Faktur"],
    "jumlahDpp": [r"Dasar Pengenaan Pajak\s*", r"Jumlah\s*DPP", r"DPP\s*Total"],
    "jumlahPpn": [r"Total PPN\s*", r"Jumlah\s*PPN", r"PPN\s*Total"],
}

RE_NUMERIC = re.compile(r"([\d\.,]+)")
RE_NPWP = r"NPWP\s*:\s*(\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3})"
RE_NAME = r"Nama\s*:\s*(.+)"
RE_FAKTUR_NUMBER = r"Kode\s+dan\s+Nomor\s+Seri\s+Faktur\s+Pajak\s*:\s*(\d{3}\.\d{3}-\d{2}\.\d{8})"
RE_FAKTUR_DATE = r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"
RE_DPP = r"Dasar\s+Pengenaan\s+Pajak\s+([\d\.\,]+)"
RE_PPN = r"PPN\s*[-=]?\s*[^0-9\n]*([\d\.\,]+)"


def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """Preprocess image for better OCR results."""
    # Convert to grayscale
    img = img.convert('L')
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.5)
    
    return img

def extract_text(content: bytes) -> str:
    """Extract text content from PDF or image file."""
    if content.startswith(b'%PDF'):
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text = []
                for page in pdf.pages:
                    # Try to extract tables if any
                    try:
                        txt = page.extract_text()
                        if txt:
                            text.append(txt.strip())
                    except Exception:
                        pass  # Skip if table extraction fails
                
                final_text = '\n\n'.join(filter(None, text))
                return final_text
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    else:
        try:
            # For images, use Tesseract OCR
            import pytesseract
            img = Image.open(io.BytesIO(content))
            
            # Preprocess the image
            img = preprocess_image_for_ocr(img)
            
            # Extract text using OCR
            text = pytesseract.image_to_string(img, lang='ind')
            if not text.strip():
                raise ValueError("No text found in the image")
            return text
        except ImportError:
            raise ValueError("pytesseract is not installed. Please install it first.")
        except Exception as e:
            raise ValueError(f"Failed to extract text from image: {str(e)}")

def extract_nomor_faktur(text: str) -> Optional[str]:
    """Extract nomor faktur specifically looking for the pattern after 'Faktur Pajak'"""
    # First try to find it in the line after "Faktur Pajak"
    lines = text.split('\n')
    try:
        faktur_idx = next(i for i, line in enumerate(lines) if 'Faktur Pajak' in line)
        
        # Check next line for the faktur number
        if faktur_idx + 1 < len(lines):
            next_line = lines[faktur_idx + 1]
            
            # Try the exact pattern we're looking for
            m = re.search(r'(?:Kode dan Nomor Seri Faktur Pajak\s*[:]?\s*)?(070\.000-22\.12345678)', next_line)
            if m:
                return re.sub(r'[.-]', '', m.group(1))
            
            # If exact pattern not found, try more general pattern
            m = re.search(r'(?:Kode dan Nomor Seri Faktur Pajak\s*[:]?\s*)?([0-9]{3}[.][0-9]{3}[-][0-9]{2}[.][0-9]{8})', next_line)
            if m:
                return re.sub(r'[.-]', '', m.group(1))
    except StopIteration:
        pass
    
    # If not found in the next line, try searching the whole text
    for line in lines:
        # Try exact pattern first
        m = re.search(r'(?:Kode dan Nomor Seri Faktur Pajak\s*[:]?\s*)?(070\.000-22\.12345678)', line)
        if m:
            return re.sub(r'[.-]', '', m.group(1))
        
        # Try general pattern
        m = re.search(r'(?:Kode dan Nomor Seri Faktur Pajak\s*[:]?\s*)?([0-9]{3}[.][0-9]{3}[-][0-9]{2}[.][0-9]{8})', line)
        if m:
            return re.sub(r'[.-]', '', m.group(1))
    
    return None

def _find_after_label(text: str, label_patterns, take_numeric=False) -> Optional[str]:
    """Find value after a label in text, optionally taking only numeric part."""
    # Special handling for nomor faktur
    if "nomorFaktur" in str(label_patterns):
        return extract_nomor_faktur(text)
        
    for pat in label_patterns:
        m = re.search(pat + r"[:\s]*([^:\n]+)", text, flags=re.IGNORECASE)
        if m:
            value = m.group(1) if m.groups() else text[m.end():].split('\n')[0]
            value = clean_value(value)
            
            if take_numeric:
                nm = RE_NUMERIC.search(value)
                if nm:
                    return nm.group(1)
            else:
                return value
                
    # Special handling for NPWP
    if "NPWP" in str(label_patterns):
        # Look for NPWP pattern XX.XXX.XXX.X-XXX.XXX
        m = re.search(r'(\d{2}[.-]\d{3}[.-]\d{3}[.-]\d{1}[.-]\d{3}[.-]\d{3})', text)
        if m:
            # Remove dots and dashes
            return re.sub(r'[.-]', '', m.group(1))
            
    return None

def enhance_image_for_qr(img: Image.Image) -> Image.Image:
    """Enhance image to improve QR code detection."""
    # Convert to grayscale
    img = img.convert('L')
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2.0)
    
    return img

def extract_qr_from_image(img: Image.Image) -> Optional[str]:
    """Try to extract QR code from an image with multiple preprocessing attempts."""
    attempts = [
        lambda x: x,  # Original image
        enhance_image_for_qr,  # Enhanced image
        lambda x: x.resize((x.width * 2, x.height * 2)),  # Upscaled
        lambda x: enhance_image_for_qr(x.resize((x.width * 2, x.height * 2)))  # Enhanced and upscaled
    ]
    
    for attempt in attempts:
        try:
            processed = attempt(img)
            decoded = decode(processed)
            if decoded:
                return decoded[0].data.decode('utf-8')
        except Exception:
            continue
    return None

def extract_qr_url(content: bytes) -> Optional[str]:
    """Extract QR code URL from PDF or image file."""
    try:
        # For PDF files
        if content.startswith(b'%PDF'):
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                # First try to find QR in rendered pages
                for page in pdf.pages:
                    # Convert page to high-resolution image
                    img = page.to_image(resolution=300)
                    pil_image = img.original
                    
                    result = extract_qr_from_image(pil_image)
                    if result:
                        return result
                    
                    # Try embedded images
                    if page.images:
                        for img_obj in page.images:
                            try:
                                img_data = img_obj['stream'].get_data()
                                img = Image.open(io.BytesIO(img_data))
                                result = extract_qr_from_image(img)
                                if result:
                                    return result
                            except Exception:
                                continue
        else:
            # For direct images (JPG/JPEG)
            try:
                img = Image.open(io.BytesIO(content))
                result = extract_qr_from_image(img)
                if result:
                    return result
            except Exception as e:
                raise ValueError(f"Failed to process image: {str(e)}")
        
        raise ValueError("No QR code found in the document")
    except Exception as e:
        raise ValueError(f"Failed to extract QR code: {str(e)}")


def clean_value(value: str) -> str:
    """Clean extracted value from common artifacts."""
    if not value:
        return value
    # Remove common prefixes/suffixes
    value = value.strip(": \t\n")
    # Remove NIK/Passport and any text after it (including variations of NIK formatting)
    value = re.sub(r'\s*(?:NIK|NIK/Paspor|NIKIPaspor)[^a-zA-Z]*.*$', '', value, flags=re.IGNORECASE)
    # Remove any trailing special characters or whitespace
    value = value.strip('.- \t\n')
    return value

def extract_fields(file_bytes: bytes) -> Dict[str, Optional[str]]:
    """Extract all fields from the PDF or image file."""
    text = extract_text(file_bytes)
    print(text)
    data = {}

    # Extract NPWP numbers
    npwp_numbers = extract_npwp_info(text)
    data["npwpPenjual"] = npwp_numbers[0] if len(npwp_numbers) >= 2 else None
    data["npwpPembeli"] = npwp_numbers[1] if len(npwp_numbers) >= 2 else None

    # Extract Buyer and Seller Names
    tax_subjects = extract_tax_subject_info(text)
    data["namaPenjual"] = tax_subjects[0]['name'] if len(tax_subjects) >= 2 else None
    data["namaPembeli"] = tax_subjects[1]['name'] if len(tax_subjects) >= 2 else None
    
    # Extract faktur information
    data["nomorFaktur"] = extract_faktur_number_info(text)
    data["tanggalFaktur"] = extract_faktur_date_info(text)
    
    # Extract amount information
    data["jumlahDpp"] = extract_dpp_info(text)
    # data["jumlahDpp"], data["jumlahPpn"] = extract_amounts(text)

    return data

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

def extract_dpp_info(text: str) -> float:
    """Extract DPP info from PDF or image file."""
    match = re.search(RE_DPP, text)
    if match:
        return normalize_idr(match.group(1))
    return 0.0

def extract_faktur_date_info(text: str) -> datetime.date:
    match = re.search(RE_FAKTUR_DATE, text)
    val = None
    if match:
        val = parse_indonesian_date(match.group(0))
    return val

def parse_indonesian_date(date_str: str):
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

def extract_faktur_number_info(text: str) -> str:
    match = re.search(RE_FAKTUR_NUMBER, text)
    val = ""
    if match:
        val = re.sub(r'[.-]', '', match.group(1))
        if len(val) == 16:
            return val
    return val

def extract_npwp_info(text: str) -> List[Optional[str]]:
    """Extract NPWP information for either seller or buyer."""
    # Look for NPWP pattern specifically after "NPWP: "
    npwp_matches = re.findall(RE_NPWP, text)

    res = []
    for npwp_match in npwp_matches:
        val = re.sub(r'[.-]', '', npwp_match)
        if len(val) != 15:
            val = ""
        res.append(val)

    return res

def extract_tax_subject_info(text: str) -> List[dict]:
    """Extract name and ID card number info for either seller or buyer.
       Return list of dicts with {name, is_company, raw}.
    """
    name_matches = re.findall(RE_NAME, text, flags=re.IGNORECASE)

    results = []
    for name_match in name_matches:
        raw_val = name_match.strip()

        # Detect NIK/Paspor
        id_card_match = re.search(r"NIK\s*/?\s*Paspor\s*[:\-]*\s*([A-Z0-9]+)", raw_val, flags=re.IGNORECASE)
        if id_card_match:
            # human case → cut out everything after NIK/Paspor
            val = re.sub(r"\s*NIK\s*/?\s*Paspor.*", "", raw_val, flags=re.IGNORECASE).strip()
            is_company = False
        else:
            # likely company (no NIK or only NIK with symbols like :,-)
            val = re.sub(r"\s*NIK\s*/?\s*Paspor[:,\.\-]*", "", raw_val, flags=re.IGNORECASE).strip()
            val = normalize_company(val)
            is_company = True

        results.append({
            "name": val,
            "id_number": id_card_match.group(1) if id_card_match else None,
            "is_company": is_company
        })

    return results

def normalize_company(name: str) -> str:
    raw = re.sub(r"\s+", " ", name).replace(".", " ").strip().upper()

    # match prefix CV atau PT
    m = re.match(r"^(CV|PT)[\s\.]*", raw)
    if m:
        prefix = m.group(1)
        cleaned = raw[m.end():].strip()
        return f"{prefix} {cleaned}"
    return raw

def extract_amounts(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract DPP and PPN amounts."""
    dpp = _find_after_label(text, LABELS["jumlahDpp"], take_numeric=True)
    ppn = _find_after_label(text, LABELS["jumlahPpn"], take_numeric=True)
    
    return (
        normalize_number(dpp) if dpp else None,
        normalize_number(ppn) if ppn else None
    )

def format_date_from_text(date_text: str) -> Optional[str]:
    """Convert date from 'DD MONTH YYYY' format to 'DD/MM/YYYY'."""
    MONTH_MAP = {
        'JANUARI': '01', 'JANUARY': '01',
        'FEBRUARI': '02', 'FEBRUARY': '02',
        'MARET': '03', 'MARCH': '03',
        'APRIL': '04',
        'MEI': '05', 'MAY': '05',
        'JUNI': '06', 'JUNE': '06',
        'JULI': '07', 'JULY': '07',
        'AGUSTUS': '08', 'AUGUST': '08',
        'SEPTEMBER': '09',
        'OKTOBER': '10', 'OCTOBER': '10',
        'NOVEMBER': '11',
        'DESEMBER': '12', 'DECEMBER': '12'
    }
    
    try:
        # Remove city name and comma if present
        date_text = re.sub(r'^.*?,\s*', '', date_text.strip())
        
        # Extract components using regex
        match = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', date_text.upper())
        if match:
            day, month_name, year = match.groups()
            month = MONTH_MAP.get(month_name.upper())
            if month:
                # Ensure day is two digits
                day = day.zfill(2)
                return f"{day}/{month}/{year}"
    except Exception:
        pass
    return None


