-+0fhjklwerty`2`    qabd
1   # backend/models/drawing.py  — Pydantic models for all data structures

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class OCRDetection(BaseModel):
    id: str
    text: str
    type: str = "unknown"
    bbox: list[int]          # [x1, y1, x2, y2]
    confidence: float
    page: int = 1


class FieldValue(BaseModel):
    value: str
    bbox: list[int]
    confidence: float
    id: str = ""


class BOMRow(BaseModel):
    item_no:     str
    part_number: str
    quantity:    str
    description: str = ""
    bbox:        list[int] = []
    confidence:  float = 0.0


class DrawingMeta(BaseModel):
    doc_id:       str
    drawing_id:   str
    display_name: str
    drawing_type: str = ""   # "part" | "assembly"
    page_num:     int  = 1
    image_path:   str  = ""
    annotated_path: str = ""
    output_dir:   str  = ""


class ChecklistRequirement(BaseModel):
    requirement: str
    expected:    str = "Required"
    notes:       str = ""


class ValidationRow(BaseModel):
    requirement: str
    expected:    str
    found:       str
    status:      str    # "✓" | "✗" | "NA"


class DrawingPayload(BaseModel):
    company_name:  str = "Custom"
    checklist_id:  str = ""


class ValidateRequest(BaseModel):
    doc_id:      str
    drawing_id:  str
    checklist_id: str = ""


class ChatRequest(BaseModel):
    doc_id:      str
    drawing_id:  str
    question:    str
    history:     list[dict] = []


class SearchRequest(BaseModel):
    doc_id:     str
    drawing_id: str
    query:      str
