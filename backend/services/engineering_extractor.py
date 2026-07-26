# backend/services/engineering_extractor.py
# GPT-powered steps:
#   Step 1  — Convert raw OCR detections → structured engineering JSON
#   Step 2  — Generate a concise drawing summary paragraph
#   Step 5  — Compute drawing statistics from the structured JSON

from __future__ import annotations
import json
from services.ai_service import call_ai

# ---------------------------------------------------------------------------
# Engineering JSON schema (sent to GPT as a reference)
# ---------------------------------------------------------------------------
ENGINEERING_SCHEMA = {
    "title_block": {
        "drawing_title":  "",
        "drawing_number": "",
        "revision":       "",
        "sheet":          "",
        "scale":          "",
        "units":          "",
        "drawn_by":       "",
        "checked_by":     "",
        "approved_by":    "",
        "date":           "",
        "company":        "",
    },
    "material":          "",
    "dimensions":        [],
    "tolerances":        [],
    "gdt_symbols":       [],
    "surface_finish":    [],
    "threads":           [],
    "notes":             [],
    "general_notes":     [],
    "tables":            [],
    "other_annotations": [],
}

# ---------------------------------------------------------------------------
# Step 1 — OCR → Structured Engineering JSON
# ---------------------------------------------------------------------------

def extract_engineering_json(ocr_detections: list[dict]) -> dict:
    """
    Send raw OCR detections to GPT and receive a structured engineering JSON.

    Args:
        ocr_detections: List of {text, confidence, bbox} dicts from PaddleOCR.

    Returns:
        Parsed engineering JSON dict. On parse failure, returns error dict.
    """
    # Build a compact text list from OCR (GPT does not need bbox/confidence)
    ocr_lines = [d["text"] for d in ocr_detections if d.get("text", "").strip()]
    ocr_text  = "\n".join(ocr_lines)

    schema_str = json.dumps(ENGINEERING_SCHEMA, indent=2)

    prompt = f"""You have received the following OCR text extracted from an engineering drawing:

--- OCR TEXT START ---
{ocr_text}
--- OCR TEXT END ---

Your task:
1. Parse this OCR text carefully.
2. Populate the JSON schema below with information found ONLY in the OCR text.
3. Do NOT invent or assume any missing values.
4. Use empty strings "" for missing scalar fields.
5. Use empty arrays [] for missing list fields.
6. Return ONLY valid JSON — no markdown, no explanation.

Schema to fill:
{schema_str}

Return the completed JSON now:"""

    raw = call_ai(prompt, json_mode=True)

    # Parse the returned JSON safely
    try:
        # Strip any accidental markdown fences
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"error": "GPT returned invalid JSON", "raw_response": raw}


# ---------------------------------------------------------------------------
# Step 2 — Drawing Summary
# ---------------------------------------------------------------------------

def generate_summary(eng_json: dict) -> str:
    """
    Ask GPT to generate a concise engineering summary from the structured JSON.

    Returns:
        A short summary string (~5–10 lines).
    """
    eng_str = json.dumps(eng_json, indent=2)

    prompt = f"""Using ONLY the structured engineering drawing JSON below, 
generate a concise engineering summary that includes:

- Drawing Title
- Drawing Number  
- Material
- Revision
- Scale
- Number of dimensions detected
- Number of tolerances detected
- Number of notes
- Surface finish count
- Thread count
- Any other key observations from the drawing

Use only information present in the JSON. State "Not present" for missing fields.
Keep the summary professional and brief (no bullet walls — use short sentences).

Structured Drawing JSON:
{eng_str}

Summary:"""

    return call_ai(prompt)


# ---------------------------------------------------------------------------
# Step 5 — Statistics
# ---------------------------------------------------------------------------

def compute_statistics(eng_json: dict) -> dict:
    """
    Compute drawing statistics directly from the structured JSON (no GPT needed).

    Returns:
        Dict with count fields.
    """
    tb = eng_json.get("title_block", {})
    return {
        "dimensions":        len(eng_json.get("dimensions",        [])),
        "tolerances":        len(eng_json.get("tolerances",        [])),
        "gdt_symbols":       len(eng_json.get("gdt_symbols",       [])),
        "surface_finishes":  len(eng_json.get("surface_finish",    [])),
        "threads":           len(eng_json.get("threads",           [])),
        "notes":             len(eng_json.get("notes",             [])),
        "general_notes":     len(eng_json.get("general_notes",     [])),
        "tables":            len(eng_json.get("tables",            [])),
        "other_annotations": len(eng_json.get("other_annotations", [])),
        "has_title":         bool(tb.get("drawing_title")),
        "has_material":      bool(eng_json.get("material")),
        "has_revision":      bool(tb.get("revision")),
    }
