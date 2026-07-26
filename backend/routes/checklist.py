# backend/routes/checklist.py
import os, shutil, uuid
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from services.checklist_parser import parse_checklist, SUPPORTED
from services.context_manager import store_checklist, get_checklist, new_checklist_id, COMPANIES

router = APIRouter(prefix="/checklist", tags=["Checklist"])
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "checklists")


@router.get("/companies")
def list_companies():
    return {"companies": COMPANIES}


@router.post("/upload")
async def upload_checklist(
    company_name: str = Form(...),
    file: UploadFile = File(...),
):
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in SUPPORTED:
        raise HTTPException(400, f"Unsupported format {ext}. Allowed: {SUPPORTED}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    cl_id = new_checklist_id()
    save_path = os.path.join(UPLOAD_DIR, f"{cl_id}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        requirements = parse_checklist(save_path)
    except Exception as e:
        raise HTTPException(500, f"Checklist parse error: {e}")

    data = {
        "checklist_id":  cl_id,
        "company_name":  company_name,
        "filename":      file.filename,
        "requirements":  requirements,
        "total":         len(requirements),
    }
    store_checklist(cl_id, data)
    return JSONResponse(content=data)


@router.get("/{checklist_id}")
def get_checklist_endpoint(checklist_id: str):
    cl = get_checklist(checklist_id)
    if not cl:
        raise HTTPException(404, "Checklist not found")
    return JSONResponse(content=cl)
