# backend/services/validator.py
# Validates extracted engineering data against an uploaded checklist.
# Uses keyword matching + AI to determine pass/fail/NA per requirement.

from __future__ import annotations
import json
from services.ai_service import call_ai

# ── Part-only fields (NA for assembly) ───────────────────────────────────────
PART_ONLY = {"material", "surface finish", "projection", "tolerance", "dimension",
             "geometric tolerance", "scale"}
# ── Assembly-only fields ──────────────────────────────────────────────────────
ASSEMBLY_ONLY = {"bom", "bill of material", "item number", "part number", "quantity"}


def validate_drawing(
    eng_json: dict,
    drawing_type: str,
    checklist: list[dict],
) -> list[dict]:
    """
    Validate every checklist requirement against the extracted engineering JSON.

    Returns list of:
        {requirement, expected, found, status}   status = ✓ | ✗ | NA
    """
    if not checklist:
        return _auto_validate(eng_json, drawing_type)

    rows = []
    for req_item in checklist:
        req   = req_item.get("requirement", "")
        exp   = req_item.get("expected", "Required")
        notes = req_item.get("notes", "")
        if not req.strip():
            continue

        status, found = _evaluate_requirement(req, exp, eng_json, drawing_type)
        rows.append({
            "requirement": req,
            "expected":    exp,
            "found":       found,
            "status":      status,
            "notes":       notes,
        })

    return rows


def _evaluate_requirement(req: str, expected: str,
                           eng_json: dict, drawing_type: str) -> tuple[str, str]:
    """Return (status, found_value) for a single requirement."""
    req_lower = req.lower()

    # NA logic — wrong drawing type
    if drawing_type == "assembly" and any(k in req_lower for k in PART_ONLY):
        return "NA", "N/A"
    if drawing_type == "part" and any(k in req_lower for k in ASSEMBLY_ONLY):
        return "NA", "N/A"

    # Extract relevant data from eng_json
    found = _extract_for_req(req_lower, eng_json, drawing_type)

    if expected.lower() in ("n/a", "na", "not applicable"):
        return "NA", "N/A"

    if found and found not in ("", "Not present"):
        return "✓", found
    return "✗", "Missing"


def _extract_for_req(req_lower: str, eng_json: dict, drawing_type: str) -> str:
    """Try to extract a value from eng_json relevant to the requirement keyword."""
    tb = eng_json.get("title_block", {})

    LOOKUP = {
        "drawing number":  _val(tb.get("drawing_number")),
        "drawing title":   _val(tb.get("drawing_title")),
        "title":           _val(tb.get("drawing_title")),
        "revision":        _val(tb.get("revision")),
        "rev":             _val(tb.get("revision")),
        "scale":           _val(tb.get("scale")),
        "date":            _val(tb.get("date")),
        "drawn by":        _val(tb.get("drawn_by")),
        "checked by":      _val(tb.get("checked_by")),
        "approved by":     _val(tb.get("approved_by")),
        "material":        eng_json.get("material", ""),
        "dimension":       f"{len(eng_json.get('dimensions', []))} found",
        "tolerance":       f"{len(eng_json.get('tolerances', []))} found",
        "surface finish":  f"{len(eng_json.get('surface_finish', []))} found",
        "thread":          f"{len(eng_json.get('threads', []))} found",
        "note":            f"{len(eng_json.get('notes', []))} found",
        "general note":    f"{len(eng_json.get('general_notes', []))} found",
        "gdt":             f"{len(eng_json.get('gdt_symbols', []))} found",
        "geometric":       f"{len(eng_json.get('gdt_symbols', []))} found",
        "projection":      _val(eng_json.get("projection_method")),
        "bom":             f"{len(eng_json.get('bill_of_materials', []))} rows",
        "bill of material":f"{len(eng_json.get('bill_of_materials', []))} rows",
        "item number":     f"{len(eng_json.get('bill_of_materials', []))} rows",
        "part number":     f"{len(eng_json.get('bill_of_materials', []))} rows",
        "quantity":        f"{len(eng_json.get('bill_of_materials', []))} rows",
        "sheet":           _val(tb.get("sheet")),
        "units":           _val(tb.get("units")),
        "company":         _val(tb.get("company")),
    }

    for keyword, value in LOOKUP.items():
        if keyword in req_lower:
            # Check for zero-count situations
            if isinstance(value, str) and value.endswith("0 found"):
                return ""
            if isinstance(value, str) and value.endswith("0 rows"):
                return ""
            return value or ""

    return ""


def _val(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return str(v.get("value", ""))
    return str(v)


def _auto_validate(eng_json: dict, drawing_type: str) -> list[dict]:
    """Generate a default validation table when no checklist is uploaded."""
    tb = eng_json.get("title_block", {})
    checks = [
        ("Drawing Title",   _val(tb.get("drawing_title"))),
        ("Drawing Number",  _val(tb.get("drawing_number"))),
        ("Revision",        _val(tb.get("revision"))),
        ("Scale",           _val(tb.get("scale"))),
        ("Date",            _val(tb.get("date"))),
        ("Drawn By",        _val(tb.get("drawn_by"))),
    ]
    if drawing_type == "part":
        checks += [
            ("Material",        eng_json.get("material", "")),
            ("Dimensions",      f"{len(eng_json.get('dimensions',[]))} found"),
            ("Tolerances",      f"{len(eng_json.get('tolerances',[]))} found"),
            ("Surface Finish",  f"{len(eng_json.get('surface_finish',[]))} found"),
            ("Threads",         f"{len(eng_json.get('threads',[]))} found"),
            ("GD&T Symbols",    f"{len(eng_json.get('gdt_symbols',[]))} found"),
            ("General Notes",   f"{len(eng_json.get('general_notes',[]))} found"),
        ]
    else:  # assembly
        bom = eng_json.get("bill_of_materials", [])
        checks += [
            ("BOM",            f"{len(bom)} rows" if bom else ""),
            ("General Notes",  f"{len(eng_json.get('general_notes',[]))} found"),
        ]

    rows = []
    for req, found in checks:
        if not found or found.startswith("0 "):
            status, found_disp = "✗", "Missing"
        else:
            status, found_disp = "✓", found
        rows.append({"requirement": req, "expected": "Required",
                     "found": found_disp, "status": status, "notes": ""})
    return rows


def compute_score(rows: list[dict]) -> float:
    """Return percentage of ✓ rows (NA excluded from denominator)."""
    applicable = [r for r in rows if r.get("status") != "NA"]
    if not applicable:
        return 0.0
    passed = sum(1 for r in applicable if r.get("status") == "✓")
    return round(passed / len(applicable) * 100, 1)
