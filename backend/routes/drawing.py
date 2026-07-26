# backend/routes/drawing.py
# Full pipeline — NO image annotation/generation at all.
# Highlight returns JSON coordinates only.

from __future__ import annotations
import os, shutil
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse

from services.context_manager import (
    new_doc_id, create_drawing, get_drawing, list_drawings,
    get_checklist, save_drawing_json,
)
from services.batch_processor       import process_upload
from services.ocr_service           import run_ocr_on_image
from services.classifier            import classify_drawing
from services.engineering_extractor import extract_engineering_json, generate_summary
from services.ocr_db                import build_ocr_db, link_fields_to_ocr
from services.rule_engine           import run_rule_engine
from services.search_engine         import build_index
import numpy as np
from PIL import Image

router = APIRouter(tags=["Drawings"])
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")


@router.post("/upload-drawing")
async def upload_drawing(
    company_name: str = Form(default="Custom"),
    checklist_id: str = Form(default=""),
    file: UploadFile = File(...),
):
    doc_id = new_doc_id()
    save_dir = os.path.join(UPLOAD_DIR, doc_id)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, file.filename)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        pages = process_upload(save_path, doc_id)
    except Exception as e:
        raise HTTPException(500, f"Batch split error: {e}")

    checklist_data = get_checklist(checklist_id) if checklist_id else None
    checklist_reqs = checklist_data.get("requirements", []) if checklist_data else []

    results = []
    for page in pages:
        ctx = create_drawing(doc_id=doc_id, display_name=page["display_name"],
                             page_num=page["page_num"], company_name=company_name)
        ctx.image_path   = page["image_path"]
        ctx.checklist_id = checklist_id

        # ── OCR ───────────────────────────────────────────────────────────────
        img_pil = Image.open(ctx.image_path).convert("RGB")
        nat_w, nat_h = img_pil.size                    # store natural size
        img_arr = np.array(img_pil)
        raw_ocr = run_ocr_on_image(img_arr)

        for i, det in enumerate(raw_ocr):
            det["id"]   = f"{ctx.drawing_id}_TXT_{i:04d}"
            det["page"] = ctx.page_num
            det.setdefault("type", "ocr")

        ctx.ocr_results = raw_ocr

        # ── OCR Coordinate DB ─────────────────────────────────────────────────
        ctx.ocr_db = build_ocr_db(raw_ocr)
        # Store natural image dimensions inside OCR DB meta
        ctx.ocr_db["__meta__"] = {"nat_w": nat_w, "nat_h": nat_h}
        save_drawing_json(ctx, "ocr_db", ctx.ocr_db)
        save_drawing_json(ctx, "ocr", raw_ocr)

        # ── Classify ──────────────────────────────────────────────────────────
        ctx.drawing_type = classify_drawing(raw_ocr)

        # ── AI Extraction ──────────────────────────────────────────────────────
        try:
            eng_json = extract_engineering_json(raw_ocr)
            summary  = generate_summary(eng_json)
        except Exception as e:
            eng_json = {"error": str(e)}
            summary  = "AI extraction failed."

        # ── Link fields to OCR IDs ────────────────────────────────────────────
        linked_json = link_fields_to_ocr(eng_json, ctx.ocr_db)
        confidences = [d.get("confidence", 0) for d in raw_ocr]
        linked_json["_ocr_meta"] = {"confidences": confidences,
                                    "nat_w": nat_w, "nat_h": nat_h}

        # ── Rule Engine ────────────────────────────────────────────────────────
        rule_result = run_rule_engine(linked_json, ctx.drawing_type,
                                      company_name, checklist_reqs)
        ctx.eng_json        = rule_result["normalized_json"]
        ctx.validation_rows = rule_result["validation_rows"]
        ctx.rule_violations = rule_result["rule_violations"]
        ctx.quality_score   = rule_result["quality_score"]
        ctx.validation_score = rule_result["quality_score"].get("checklist_compliance", 0)

        save_drawing_json(ctx, "extracted", {
            "engineering_json": ctx.eng_json,
            "summary": summary,
            "quality_score": ctx.quality_score,
            "nat_w": nat_w, "nat_h": nat_h,
        })
        save_drawing_json(ctx, "validation", {
            "rows": ctx.validation_rows,
            "score": ctx.validation_score,
            "quality_score": ctx.quality_score,
            "rule_violations": ctx.rule_violations,
        })

        # ── Search index ──────────────────────────────────────────────────────
        ctx.search_index = build_index(raw_ocr, ctx.eng_json)

        results.append({
            "drawing_id":       ctx.drawing_id,
            "display_name":     ctx.display_name,
            "drawing_type":     ctx.drawing_type,
            "page_num":         ctx.page_num,
            "ocr_count":        len(raw_ocr),
            "nat_w":            nat_w,
            "nat_h":            nat_h,
            "validation_score": ctx.validation_score,
            "quality_score":    ctx.quality_score,
            "rule_violations":  ctx.rule_violations,
            "summary":          summary,
        })

    return JSONResponse(content={"doc_id": doc_id, "company": company_name,
                                 "total": len(results), "drawings": results})


# ── Highlight — returns JSON coordinates ONLY, no image generation ────────────
@router.get("/highlight")
def get_highlight(
    doc_id:     str = Query(...),
    drawing_id: str = Query(...),
    ocr_id:     str = Query(default=""),
    field_name: str = Query(default=""),
):
    """
    Return bounding box coordinates for a field. NEVER generates an image.
    Frontend is responsible for drawing the rectangle on its canvas.

    Response: {id, text, bbox:[x1,y1,x2,y2], page, nat_w, nat_h}
    nat_w/nat_h = original image dimensions so frontend can compute scale.
    """
    ctx = get_drawing(doc_id, drawing_id)
    if not ctx:
        raise HTTPException(404, "Drawing not found")

    meta = ctx.ocr_db.get("__meta__", {})
    nat_w = meta.get("nat_w", 0)
    nat_h = meta.get("nat_h", 0)

    # ── Priority 1: direct OCR ID ─────────────────────────────────────────────
    if ocr_id and ocr_id in ctx.ocr_db:
        e = ctx.ocr_db[ocr_id]
        return JSONResponse(content={
            "id": ocr_id, "text": e["text"],
            "bbox": e["bbox"], "page": e.get("page", ctx.page_num),
            "nat_w": nat_w, "nat_h": nat_h,
        })

    # ── Priority 2: field name → eng_json → ocr_id ────────────────────────────
    if field_name:
        result = _find_field_coords(ctx, field_name)
        if result:
            result.update({"nat_w": nat_w, "nat_h": nat_h})
            return JSONResponse(content=result)

        # Fallback: text search in OCR DB
        fl = field_name.lower()
        for oid, entry in ctx.ocr_db.items():
            if oid == "__meta__":
                continue
            if fl in entry.get("text", "").lower():
                return JSONResponse(content={
                    "id": oid, "text": entry["text"],
                    "bbox": entry["bbox"], "page": entry.get("page", ctx.page_num),
                    "nat_w": nat_w, "nat_h": nat_h,
                })

    raise HTTPException(404,
        f"No coordinates found. ocr_id='{ocr_id}' field='{field_name}'. "
        f"OCR DB has {len(ctx.ocr_db)-1} entries.")


def _find_field_coords(ctx, field_name: str) -> dict | None:
    """Walk eng_json recursively to find a field and its OCR coordinates."""
    target = field_name.lower().replace(" ", "_")
    eng = ctx.eng_json

    def _walk(obj, key_path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "__meta__":
                    continue
                match = k.lower().replace(" ", "_") == target
                if match:
                    ocr_id = v.get("ocr_id", "") if isinstance(v, dict) else ""
                    bbox   = v.get("bbox", [])    if isinstance(v, dict) else []
                    val    = v.get("value", str(v)) if isinstance(v, dict) else str(v)
                    # Try OCR DB for bbox if not in field
                    if not bbox and ocr_id and ocr_id in ctx.ocr_db:
                        bbox = ctx.ocr_db[ocr_id]["bbox"]
                    if bbox:
                        return {"id": ocr_id or target, "text": val,
                                "bbox": bbox, "page": ctx.page_num}
                result = _walk(v, k)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = _walk(item)
                if result:
                    return result
        return None

    return _walk(eng)


# ── OCR DB endpoint ───────────────────────────────────────────────────────────
@router.get("/ocr-db/{doc_id}/{drawing_id}")
def get_ocr_db(doc_id: str, drawing_id: str):
    ctx = get_drawing(doc_id, drawing_id)
    if not ctx:
        raise HTTPException(404, "Drawing not found")
    entries = {k: v for k, v in ctx.ocr_db.items() if k != "__meta__"}
    return JSONResponse(content={"drawing_id": drawing_id,
                                 "total": len(entries), "ocr_db": entries})


# ── Data endpoints ────────────────────────────────────────────────────────────
@router.get("/drawings/{doc_id}")
def list_doc_drawings(doc_id: str):
    drawings = list_drawings(doc_id)
    if not drawings:
        raise HTTPException(404, f"No drawings for doc_id={doc_id}")
    return JSONResponse(content={"doc_id": doc_id, "drawings": [{
        "drawing_id": d.drawing_id, "display_name": d.display_name,
        "drawing_type": d.drawing_type, "validation_score": d.validation_score,
        "quality_score": d.quality_score, "ocr_count": len(d.ocr_results),
    } for d in drawings]})


@router.get("/drawing/{doc_id}/{drawing_id}")
def get_drawing_data(doc_id: str, drawing_id: str):
    ctx = get_drawing(doc_id, drawing_id)
    if not ctx:
        raise HTTPException(404, "Drawing not found")
    meta = ctx.ocr_db.get("__meta__", {})
    return JSONResponse(content={
        "doc_id": ctx.doc_id, "drawing_id": ctx.drawing_id,
        "display_name": ctx.display_name, "drawing_type": ctx.drawing_type,
        "company_name": ctx.company_name, "ocr_count": len(ctx.ocr_results),
        "ocr_db_size": len(ctx.ocr_db) - 1,
        "nat_w": meta.get("nat_w", 0), "nat_h": meta.get("nat_h", 0),
        "eng_json": ctx.eng_json, "validation_rows": ctx.validation_rows,
        "validation_score": ctx.validation_score, "quality_score": ctx.quality_score,
        "rule_violations": ctx.rule_violations,
    })


@router.get("/image/{doc_id}/{drawing_id}")
def get_image(doc_id: str, drawing_id: str):
    ctx = get_drawing(doc_id, drawing_id)
    if not ctx or not os.path.exists(ctx.image_path or ""):
        raise HTTPException(404, "Image not found")
    return FileResponse(ctx.image_path, media_type="image/png")
