from pydantic import BaseModel
from typing import Any, List, Optional, Literal


class Deviation(BaseModel):
    field: str
    pdf_value: Optional[Any]
    djp_api_value: Optional[Any]
    deviation_type: Literal["mismatch","missing_in_pdf","missing_in_api"]

class ValidatedData(BaseModel):
    npwpPenjual: Optional[str] = None
    namaPenjual: Optional[str] = None
    npwpPembeli: Optional[str] = None
    namaPembeli: Optional[str] = None
    nomorFaktur: Optional[str] = None
    tanggalFaktur: Optional[str] = None
    jumlahDpp: Optional[str] = None
    jumlahPpn: Optional[str] = None

class ValidationResults(BaseModel):
    status: Literal["validated_with_deviations", "validated_successfully", "error"]
    message: str
    validation_results: dict = {
        "deviations": List[Deviation],
        "validated_data": ValidatedData
    }