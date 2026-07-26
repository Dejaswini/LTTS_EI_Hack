# backend/services/context_manager.py
# Central in-memory store for per-drawing isolated contexts.
# Each drawing has its own complete independent data store.

from __future__ import annotations
import os, json, uuid
from dataclasses import dataclass, field

# ── Global store ─────────────────────────────────────────────────────────────
# STORE[doc_id][drawing_id] = DrawingContext
STORE: dict[str, dict[str, "DrawingContext"]] = {}

# Checklist store: checklist_id -> list of requirement dicts
CHECKLISTS: dict[str, dict] = {}

COMPANIES = ["LTTS", "Bosch", "Hyundai", "TVS", "Ashok Leyland", "Custom Company"]
BASE_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "outputs")


@dataclass
class DrawingContext:
    doc_id:          str
    drawing_id:      str
    display_name:    str
    company_name:    str        = "Custom"
    drawing_type:    str        = ""
    page_num:        int        = 1
    image_path:      str        = ""
    annotated_path:  str        = ""
    output_dir:      str        = ""
    # OCR
    ocr_results:     list       = field(default_factory=list)
    ocr_db:          dict       = field(default_factory=dict)   # id -> {text,bbox,conf,page}
    # AI extraction
    eng_json:        dict       = field(default_factory=dict)
    # Validation
    checklist_id:    str        = ""
    validation_rows: list       = field(default_factory=list)
    validation_score: float     = 0.0
    quality_score:   dict       = field(default_factory=dict)
    rule_violations: list       = field(default_factory=list)
    # Search index: keyword -> list of {field_id, text, bbox, type}
    search_index:    dict       = field(default_factory=dict)
    # Chat history for this drawing
    chat_history:    list       = field(default_factory=list)


# ── Drawing context helpers ───────────────────────────────────────────────────

def new_doc_id() -> str:
    return "DOC" + uuid.uuid4().hex[:6].upper()

def new_drawing_id(doc_id: str) -> str:
    n = len(STORE.get(doc_id, {})) + 1
    return f"{doc_id}_DRW{n:03d}"

def get_or_create_doc(doc_id: str) -> dict:
    if doc_id not in STORE:
        STORE[doc_id] = {}
    return STORE[doc_id]

def create_drawing(doc_id: str, display_name: str, page_num: int = 1,
                   company_name: str = "Custom") -> DrawingContext:
    drawings = get_or_create_doc(doc_id)
    drawing_id = new_drawing_id(doc_id)
    out_dir = os.path.join(BASE_OUTPUT, doc_id, drawing_id)
    for sub in ["json", "annotated", "ocr", "validation"]:
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    ctx = DrawingContext(
        doc_id=doc_id, drawing_id=drawing_id,
        display_name=display_name, company_name=company_name,
        page_num=page_num, output_dir=out_dir,
    )
    drawings[drawing_id] = ctx
    return ctx

def get_drawing(doc_id: str, drawing_id: str) -> DrawingContext | None:
    return STORE.get(doc_id, {}).get(drawing_id)

def list_drawings(doc_id: str) -> list[DrawingContext]:
    return list(STORE.get(doc_id, {}).values())

def save_drawing_json(ctx: DrawingContext, name: str, data: dict | list):
    path = os.path.join(ctx.output_dir, "json", f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path

def load_drawing_json(ctx: DrawingContext, name: str) -> dict | list | None:
    path = os.path.join(ctx.output_dir, "json", f"{name}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


# ── Checklist helpers ─────────────────────────────────────────────────────────

def store_checklist(checklist_id: str, data: dict):
    CHECKLISTS[checklist_id] = data

def get_checklist(checklist_id: str) -> dict | None:
    return CHECKLISTS.get(checklist_id)

def new_checklist_id() -> str:
    return "CL" + uuid.uuid4().hex[:8].upper()
