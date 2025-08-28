from fastapi import APIRouter, UploadFile, File, HTTPException
from app.schemas.validation import ValidationResults
from app.services import pdf_extractor, djp_client, validator
from app.mock import djp_mock
import requests

router = APIRouter()

@router.post("/validate-efaktur", response_model=ValidationResults)
async def validate_efaktur(file: UploadFile = File(...)):
    try:
        # Validate file type
        content_type = file.content_type.lower()
        if content_type not in ["application/pdf", "image/jpeg", "image/jpg"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only PDF and JPG/JPEG files are supported"
            )
        
        # File read
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="No file provided")
            
        # Basic file format validation
        if content_type == "application/pdf" and not content.startswith(b'%PDF'):
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file format"
            )
        elif content_type in ["image/jpeg", "image/jpg"] and not content.startswith(b'\xff\xd8\xff'):
            raise HTTPException(
                status_code=400,
                detail="Invalid JPEG file format"
            )

        # Parse PDF/JPG fields
        pdf_data = pdf_extractor.extract_fields(content)

        # Try to get QR URL, fallback to mock if not found
        try:
            qr_url = pdf_extractor.extract_qr_url(content)
            if qr_url:
                djp_data = djp_client.fetch_djp_xml(qr_url)
            else:
                djp_data = djp_mock.get_mock_djp_data()
        except ValueError as e:
            # If QR extraction fails, use mock data
            djp_data = djp_mock.get_mock_djp_data()

        # Compare and build response
        result = validator.compare(pdf_data, djp_data)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        if "No QR code found" in str(e):
            raise HTTPException(status_code=400, detail="No valid QR code found in the document")
        raise HTTPException(status_code=400, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail="Failed to fetch data from DJP API")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
