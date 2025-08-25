# E-Faktur Validation Service (FastAPI)

Clean-architecture style microservice that validates an uploaded e-Faktur PDF/JPG against DJP mock API.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open Swagger: http://127.0.0.1:8000/docs

## Endpoint

`POST /api/v1/validate-efaktur` (multipart/form-data)
- field: `file` (PDF/JPG)

## Notes
- Still have problem with low image quality
