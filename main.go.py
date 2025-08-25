from fastapi import FastAPI
from app.api.v1.endpoints.validate import router as validate_router


app = FastAPI(title="E-Faktur Validation Service", version="1.0.0")

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(validate_router, prefix="/api/v1")
