from fastapi import APIRouter

import schemas

router = APIRouter()

@router.get("/validate-efaktur")
async def validate_efaktur():
    pass