# backend/routes/upload.py
# Defines the two API endpoints:
#   POST /upload       — accepts a drawing file, runs the full pipeline
#   GET  /result/{fn}  — returns a previously saved result JSON

from __future__ import annotations
import os
import shutil

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from services.ocr_service import extract_ocr_from_file
from services.classifier import classify_drawing
from services.part_parser import parse_part_drawing
from services.assembly_parser import parse_assembly_drawing
from services.json_generator import generate_json, load_result

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


@router.post("/upload", tags=["Pipeline"])
async def upload_drawing(file: UploadFile = File(...)):
    """
    Main pipeline endpoint.

    1. Save the uploaded file.
    2. Run PaddleOCR to extract all text detections.
    3. Classify the drawing as 'part' or 'assembly'.
    4. Parse the appropriate structured fields.
    5. Persist the output JSON and return it.
    """
    # --- Validate extension --------------------------------------------------
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # --- Save uploaded file --------------------------------------------------
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    save_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # --- OCR -----------------------------------------------------------------
    try:
        detections = extract_ocr_from_file(save_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")

    if not detections:
        raise HTTPException(
            status_code=422,
            detail="OCR returned no text. The file may be blank or unreadable.",
        )

    # --- Classification ------------------------------------------------------
    drawing_type = classify_drawing(detections)

    # --- Parsing -------------------------------------------------------------
    if drawing_type == "assembly":
        parsed_data = parse_assembly_drawing(detections)
    else:
        parsed_data = parse_part_drawing(detections)

    # --- JSON generation & persistence ---------------------------------------
    output, saved_filename = generate_json(
        drawing_type=drawing_type,
        parsed_data=parsed_data,
        original_filename=file.filename,
        raw_detections=detections,
    )

    return JSONResponse(
        content={
            "drawing_type":   drawing_type,
            "output_file":    saved_filename,
            "extracted_data": output["extracted_data"],
            "meta":           output["meta"],
        }
    )


@router.get("/result/{filename}", tags=["Results"])
def get_result(filename: str):
    """
    Retrieve a previously generated JSON result by its filename.
    """
    data = load_result(filename)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Result '{filename}' not found.")
    return JSONResponse(content=data)


@router.get("/results", tags=["Results"])
def list_results():
    """List all available result JSON filenames in the output directory."""
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    if not os.path.exists(output_dir):
        return {"files": []}
    files = [f for f in os.listdir(output_dir) if f.endswith(".json")]
    return {"files": sorted(files)}
