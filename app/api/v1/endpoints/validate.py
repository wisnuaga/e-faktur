from fastapi import APIRouter, UploadFile, File, HTTPException
from app.schemas.validation import ValidationResults
from app.services import pdf_extractor


router = APIRouter()

@router.get("/validate-efaktur", response_model=ValidationResults)
async def validate_efaktur(file: UploadFile = File(...)):
    try:
        # File read
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="No file provided")

        # Parse PDF/JPG fields
        pdf_data = pdf_extractor.extract_fields(content)

        # Decode QR
        qr_url = pdf_extractor.extract_qr_url(content)

        # Fetch official DJP data

        # Compare and build response

        pass
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
