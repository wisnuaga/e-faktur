import io
import re
import pdfplumber
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from typing import Optional, Dict, List
from datetime import datetime
from app.core.normalizers import (
    normalize_number,
    normalize_idr,
    normalize_company,
    normalize_indonesian_date,
)

RE_NPWP = r"NPWP\s*:\s*(\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3})"
RE_NAME = r"Nama\s*:\s*(.+)"
RE_FAKTUR_NUMBER = r"Kode\s+dan\s+Nomor\s+Seri\s+Faktur\s+Pajak\s*:\s*(\d{3}\.\d{3}-\d{2}\.\d{8})"
RE_FAKTUR_DATE = r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"
RE_DPP = r"Dasar\s+Pengenaan\s+Pajak\s+([\d\.\,]+)"
RE_PPN = r"PPN.*?([\d\.]+,\d{2})"

indonesian_months = {
    "januari": "January",
    "februari": "February",
    "maret": "March",
    "april": "April",
    "mei": "May",
    "juni": "June",
    "juli": "July",
    "agustus": "August",
    "september": "September",
    "oktober": "October",
    "november": "November",
    "desember": "December",
}

# Extractor
def extract_fields(file_bytes: bytes) -> Dict[str, Optional[str]]:
    """Extract all fields from the PDF or image file."""
    text = extract_text(file_bytes)
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
    data["jumlahDpp"] = extract_tax_amount(text, RE_DPP)
    data["jumlahPpn"] = extract_tax_amount(text, RE_PPN)

    return data

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

def extract_tax_amount(text: str, pattern: str) -> float:
    """Extract tax value from PDF or image file."""
    match = re.search(pattern, text)
    if match:
        val = normalize_idr(match.group(1))
        return val
    return 0.0

def extract_faktur_date_info(text: str) -> Optional[datetime.date]:
    match = re.search(RE_FAKTUR_DATE, text)
    if not match:
        return None

    s = preprocess_indonesian_date(match.group(0))
    return datetime.strptime(s.title(), "%d %B %Y")

def extract_faktur_number_info(text: str) -> str:
    match = re.search(RE_FAKTUR_NUMBER, text)
    val = ""
    if match:
        val = normalize_number(match.group(1))
        if len(val) == 16:
            return val
    return val

def extract_npwp_info(text: str) -> List[Optional[str]]:
    """Extract NPWP information for either seller or buyer."""
    # Look for NPWP pattern specifically after "NPWP: "
    npwp_matches = re.findall(RE_NPWP, text)

    res = []
    for npwp_match in npwp_matches:
        val = normalize_number(npwp_match)
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

# Image Preprocessor
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

def preprocess_indonesian_date(date_str: str) -> Optional[datetime.date]:
    """Parse string date formats: dd <bulan indo> yyyy"""
    s = date_str.strip()

    parts = s.split(" ")
    if len(parts) != 3:
        return None

    parts[1] = indonesian_months.get(parts[1].lower(), "")
    if parts[1] == "":
        return None

    s = " ".join(parts)

    return datetime.strptime(s.title(), "%d %B %Y")
