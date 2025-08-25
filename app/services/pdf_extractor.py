import io
import re
import pdfplumber
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from typing import Optional, Dict, Union, Tuple
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
                for p in pdf.pages:
                    t = p.extract_text() or ""
                    text.append(t)
                return "\n".join(text)
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


def extract_fields(file_bytes: bytes) -> Dict[str, Optional[str]]:
    text = extract_text(file_bytes)

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


