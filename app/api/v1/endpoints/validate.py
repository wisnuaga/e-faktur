from http.client import HTTPException

from fastapi import APIRouter

from schemas.validation import ValidationResults

router = APIRouter()

@router.get("/validate-efaktur", response_model=ValidationResults)
async def validate_efaktur():
    try:
        # File read
        # TODO: ...

        # Parse PDF/JPG fields

        # Decode QR

        # Fetch official DJP data

        # Compare and build response

        pass
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
