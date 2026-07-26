# backend/routes/search.py
# GET /search          — search within a specific drawing
# GET /highlight       — return bbox for a specific field
# POST /ai/chat-drawing — drawing-isolated chatbot

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.context_manager import get_drawing
from services.search_engine import search
from services.ai_service import call_ai
import json

router = APIRouter(tags=["Search & Chat"])


@router.get("/search")
def search_drawing(
    doc_id:     str = Query(...),
    drawing_id: str = Query(...),
    q:          str = Query(...),
):
    """Search within a specific drawing only. Never crosses drawing boundaries."""
    ctx = get_drawing(doc_id, drawing_id)
    if not ctx:
        raise HTTPException(404, "Drawing not found")
    if not ctx.search_index:
        raise HTTPException(422, "Drawing not yet processed. Run /upload-drawing first.")

    results = search(ctx.search_index, q)
    return JSONResponse(content={
        "doc_id":       doc_id,
        "drawing_id":   drawing_id,
        "display_name": ctx.display_name,
        "query":        q,
        "total":        len(results),
        "results":      results,
    })


@router.get("/highlight")
def highlight_field(
    doc_id:     str = Query(...),
    drawing_id: str = Query(...),
    field_id:   str = Query(...),
):
    """Return bounding box coordinates for a specific field in a drawing."""
    ctx = get_drawing(doc_id, drawing_id)
    if not ctx:
        raise HTTPException(404, "Drawing not found")

    # Search OCR results for this field_id
    for det in ctx.ocr_results:
        if det.get("id") == field_id:
            return JSONResponse(content={
                "field_id":   field_id,
                "text":       det.get("text", ""),
                "bbox":       det.get("bbox", []),
                "confidence": det.get("confidence", 0),
                "type":       det.get("type", "ocr"),
            })

    # Search search index
    for entries in ctx.search_index.values():
        for e in entries:
            if e.get("field_id") == field_id:
                return JSONResponse(content=e)

    raise HTTPException(404, f"Field {field_id} not found in {drawing_id}")


class DrawingChatRequest(BaseModel):
    doc_id:     str
    drawing_id: str
    question:   str
    history:    list[dict] = []


@router.post("/ai/chat-drawing")
def chat_with_drawing(req: DrawingChatRequest):
    """
    Drawing-isolated chatbot. Only uses data from the specified drawing.
    Explicitly blocks cross-drawing queries.
    """
    ctx = get_drawing(req.doc_id, req.drawing_id)
    if not ctx:
        raise HTTPException(404, "Drawing not found")
    if not ctx.eng_json:
        raise HTTPException(422, "Drawing not yet AI-processed.")

    eng_str = json.dumps(ctx.eng_json, indent=2, ensure_ascii=False)[:6000]

    system = f"""You are an expert Mechanical CAD Drawing Assistant.

You are currently analyzing: {ctx.display_name} ({ctx.drawing_type.upper()} DRAWING)
Company: {ctx.company_name}

YOUR KNOWLEDGE SOURCE IS STRICTLY LIMITED TO THE JSON BELOW.
DO NOT use information from any other drawing, page, or document.
DO NOT answer general questions unrelated to this drawing.
If asked about another drawing, say: "Please select that drawing from the panel."
If information is not in this drawing, say: "Not present in {ctx.display_name}."

=== {ctx.display_name} — ENGINEERING DATA ===
{eng_str}
=== END ==="""

    try:
        answer = call_ai(req.question, system_override=system, history=req.history)
    except Exception as e:
        raise HTTPException(500, str(e))

    # Update this drawing's chat history
    ctx.chat_history.extend([
        {"role": "user",      "content": req.question},
        {"role": "assistant", "content": answer},
    ])

    return JSONResponse(content={
        "drawing_id":   req.drawing_id,
        "display_name": ctx.display_name,
        "answer":       answer,
    })
