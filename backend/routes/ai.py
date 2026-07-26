# backend/routes/ai.py
# AI-powered endpoints — all built on top of the existing OCR pipeline.
#
# POST /ai/extract       Step 1 — OCR detections → structured engineering JSON
# POST /ai/summary       Step 2 — Engineering summary paragraph
# POST /ai/chat          Step 3 — Drawing-locked chatbot
# POST /ai/search        Step 4 — Semantic search inside drawing JSON
# POST /ai/stats         Step 5 — Drawing statistics
# POST /ai/full          All steps at once (extract + summary + stats)

from __future__ import annotations
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.engineering_extractor import (
    extract_engineering_json,
    generate_summary,
    compute_statistics,
)
from services.chatbot import chat_with_drawing, search_drawing

router = APIRouter(prefix="/ai", tags=["AI Assistant"])

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class OCRPayload(BaseModel):
    """Raw OCR detections list."""
    detections: list[dict]


class SummaryPayload(BaseModel):
    """Structured engineering JSON."""
    engineering_json: dict


class ChatPayload(BaseModel):
    """Chat request with the engineering JSON as context."""
    question:        str
    engineering_json: dict
    history:         list[dict] = []   # [{role, content}, ...]


class SearchPayload(BaseModel):
    """Search request."""
    query:           str
    engineering_json: dict


class FullPipelinePayload(BaseModel):
    """Run all AI steps from raw OCR in one shot."""
    detections:       list[dict]
    save_as_filename: str = ""   # optional — saves to output/{name}_ai.json


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/extract", summary="Step 1 — OCR → Engineering JSON")
def extract(payload: OCRPayload):
    """
    Send raw OCR detections to GPT and receive structured engineering JSON.
    """
    _check_env()
    try:
        eng_json = extract_engineering_json(payload.detections)
        return JSONResponse(content={"engineering_json": eng_json})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summary", summary="Step 2 — Drawing Summary")
def summary(payload: SummaryPayload):
    """
    Generate a concise engineering summary from the structured JSON.
    """
    _check_env()
    try:
        text = generate_summary(payload.engineering_json)
        return JSONResponse(content={"summary": text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", summary="Step 3 — Engineering Chatbot")
def chat(payload: ChatPayload):
    """
    Answer a question using ONLY the uploaded drawing JSON.
    """
    _check_env()
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        answer = chat_with_drawing(
            question=payload.question,
            eng_json=payload.engineering_json,
            history=payload.history,
        )
        return JSONResponse(content={"answer": answer})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", summary="Step 4 — Drawing Search")
def search(payload: SearchPayload):
    """
    Semantic search inside the engineering JSON.
    """
    _check_env()
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")
    try:
        result = search_drawing(payload.query, payload.engineering_json)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stats", summary="Step 5 — Drawing Statistics")
def stats(payload: SummaryPayload):
    """
    Return count statistics computed from the structured JSON (no GPT call).
    """
    try:
        s = compute_statistics(payload.engineering_json)
        return JSONResponse(content={"statistics": s})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full", summary="All steps — Extract + Summary + Stats")
def full_pipeline(payload: FullPipelinePayload):
    """
    Run the complete AI pipeline from raw OCR:
        1. Extract structured engineering JSON
        2. Generate summary
        3. Compute statistics
    Optionally saves the engineering JSON to output/.
    """
    _check_env()
    try:
        # Step 1
        eng_json = extract_engineering_json(payload.detections)

        # Step 2
        summary_text = generate_summary(eng_json)

        # Step 5
        statistics = compute_statistics(eng_json)

        # Optionally persist to output/
        saved_file = ""
        if payload.save_as_filename:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            out_path = os.path.join(OUTPUT_DIR, payload.save_as_filename)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({
                    "engineering_json": eng_json,
                    "summary":          summary_text,
                    "statistics":       statistics,
                }, f, indent=2, ensure_ascii=False)
            saved_file = payload.save_as_filename

        return JSONResponse(content={
            "engineering_json": eng_json,
            "summary":          summary_text,
            "statistics":       statistics,
            "saved_file":       saved_file,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# API config check endpoint (UI uses this to show config status)
# ---------------------------------------------------------------------------

@router.get("/status", summary="Check AI configuration")
def ai_status():
    """Returns whether the LTTS FoundAI Responses API is correctly configured."""
    from services.ai_service import is_configured, get_deployment
    import os
    configured = is_configured()
    return {
        "configured": configured,
        "deployment": get_deployment() if configured else "(not set)",
        "endpoint":   os.getenv("LTTS_API_URL", "(not set)") if configured else "(not set)",
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _check_env():
    """Raise HTTP 503 if AI is not configured, with a helpful message."""
    from services.ai_service import is_configured
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "AI is not configured. "
                "Open backend/.env, set LTTS_API_KEY and LTTS_API_URL, "
                "then restart the backend."
            ),
        )
