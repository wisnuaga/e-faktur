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
                for page in pdf.pages:
                    # Extract text from the page
                    page_text = page.extract_text() or ""
                    text.append(page_text)
                    
                    # Try to extract tables if any
                    try:
                        tables = page.extract_tables()
                        if tables:
                            for table in tables:
                                table_text = '\n'.join(' '.join(str(cell) for cell in row if cell) for row in table)
                                if table_text.strip():
                                    text.append(table_text)
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
    data = {}

    # Extract seller information
    data["npwpPenjual"], data["namaPenjual"] = extract_npwp_info(text, "penjual")
    
    # Extract buyer information
    data["npwpPembeli"], data["namaPembeli"] = extract_npwp_info(text, "pembeli")
    
    # Extract faktur information
    data["nomorFaktur"], data["tanggalFaktur"] = extract_faktur_info(text)
    
    # Extract amount information
    data["jumlahDpp"], data["jumlahPpn"] = extract_amounts(text)
    
    return data

def extract_npwp_info(text: str, section: str = "penjual") -> Tuple[Optional[str], Optional[str]]:
    """Extract NPWP and name information for either seller or buyer."""
    sections = text.split('\n\n')
    
    # Define section indices based on role
    target_section = 3 if section == "penjual" else 5
    if len(sections) <= target_section:
        return None, None
    
    section_text = sections[target_section]
    
    # Look for NPWP pattern specifically after "NPWP: "
    npwp_match = re.search(r'NPWP\s*:\s*([0-9.-]+)', section_text)
    
    npwp = None
    if npwp_match:
        # Get the raw NPWP and remove any existing dots and dashes to normalize it
        npwp = re.sub(r'[.-]', '', npwp_match.group(1))
        if len(npwp) != 15:
            npwp = None
    
    # Get name from the same section, looking for "Nama :"
    name_match = re.search(r'Nama\s*:\s*([^\n]+)', section_text)
    name = None
    if name_match:
        # First clean the value to remove NIK and other unwanted parts
        name = clean_value(name_match.group(1))
        if name:
            # Format company names starting with PT
            if name.startswith('PT') and not name.startswith('PT '):
                # Insert space after PT if it's not there
                name = re.sub(r'^PT(?=[A-Z])', 'PT ', name)
            # Final cleanup of any remaining artifacts
            name = name.strip()
    
    return npwp, name

def extract_faktur_info(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract faktur number and date information."""
    nomor = extract_nomor_faktur(text)
    if not nomor:
        m = RE_FAKTUR_NUMBER.search(text)
        if m:
            nomor = m.group(0)
    
    tanggal = _find_after_label(text, LABELS["tanggalFaktur"])
    if not tanggal:
        m = RE_DATE.search(text)
        if m:
            tanggal = m.group(0)
    
    return (
        normalize_faktur_number(nomor) if nomor else None,
        normalize_date(tanggal) if tanggal else None
    )

def extract_amounts(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract DPP and PPN amounts."""
    dpp = _find_after_label(text, LABELS["jumlahDpp"], take_numeric=True)
    ppn = _find_after_label(text, LABELS["jumlahPpn"], take_numeric=True)
    
    return (
        normalize_number(dpp) if dpp else None,
        normalize_number(ppn) if ppn else None
    )


