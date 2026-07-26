# backend/services/field_mapper.py
# Normalizes field names from various company naming conventions
# to canonical internal field names used by the validation engine.

from __future__ import annotations
import re

# ── Canonical field aliases ───────────────────────────────────────────────────
# Maps any known alias (lowercase, stripped) → canonical name
FIELD_ALIASES: dict[str, str] = {
    # Drawing number
    "drawing number":    "drawing_number",
    "drawing no":        "drawing_number",
    "drawing no.":       "drawing_number",
    "dwg no":            "drawing_number",
    "dwg no.":           "drawing_number",
    "dwg. no":           "drawing_number",
    "dwg. no.":          "drawing_number",
    "dwg number":        "drawing_number",
    "document number":   "drawing_number",
    "doc no":            "drawing_number",
    "part number":       "part_number",
    "part no":           "part_number",
    "part no.":          "part_number",
    # Title
    "drawing title":     "drawing_title",
    "title":             "drawing_title",
    "assembly title":    "drawing_title",
    "assembly number":   "drawing_number",
    "assembly no":       "drawing_number",
    # Revision
    "revision":          "revision",
    "rev":               "revision",
    "rev.":              "revision",
    "revision no":       "revision",
    "revision number":   "revision",
    # Scale
    "scale":             "scale",
    "drawing scale":     "scale",
    # Date
    "date":              "date",
    "drawing date":      "date",
    "issue date":        "date",
    "created date":      "date",
    # People
    "drawn by":          "drawn_by",
    "drawn":             "drawn_by",
    "prepared by":       "drawn_by",
    "designed by":       "drawn_by",
    "designer":          "drawn_by",
    "checked by":        "checked_by",
    "checked":           "checked_by",
    "checker":           "checked_by",
    "verified by":       "checked_by",
    "approved by":       "approved_by",
    "approved":          "approved_by",
    "authorised by":     "approved_by",
    "authorized by":     "approved_by",
    # Material
    "material":          "material",
    "material spec":     "material",
    "raw material":      "material",
    # Surface finish
    "surface finish":    "surface_finish",
    "finish":            "surface_finish",
    "roughness":         "surface_finish",
    "surface roughness": "surface_finish",
    "ra":                "surface_finish",
    # Dimensions & tolerances
    "dimension":         "dimensions",
    "dimensions":        "dimensions",
    "dim":               "dimensions",
    "tolerance":         "tolerances",
    "tolerances":        "tolerances",
    "tol":               "tolerances",
    "general tolerance": "tolerances",
    # GD&T
    "gdt":               "gdt_symbols",
    "gd&t":              "gdt_symbols",
    "geometric tolerance":      "gdt_symbols",
    "geometric dimensioning":   "gdt_symbols",
    # Threads
    "thread":            "threads",
    "threads":           "threads",
    "thread specification": "threads",
    # Projection
    "projection":        "projection_method",
    "projection method": "projection_method",
    "projection symbol": "projection_method",
    "angle of projection": "projection_method",
    # BOM
    "bom":               "bill_of_materials",
    "bill of material":  "bill_of_materials",
    "bill of materials": "bill_of_materials",
    "parts list":        "bill_of_materials",
    "item list":         "bill_of_materials",
    # Notes
    "notes":             "notes",
    "general notes":     "general_notes",
    "note":              "notes",
    "remarks":           "notes",
    # Sheet
    "sheet":             "sheet",
    "sheet no":          "sheet",
    "sheet number":      "sheet",
    # Units
    "units":             "units",
    "unit":              "units",
    # Company
    "company":           "company",
    "organization":      "company",
}


def normalize_field_name(raw: str) -> str:
    """
    Convert any field name alias to its canonical form.
    Returns the canonical name, or the lowercased input if no match found.
    """
    key = raw.strip().lower()
    return FIELD_ALIASES.get(key, key.replace(" ", "_"))


def normalize_checklist(requirements: list[dict]) -> list[dict]:
    """
    Normalize requirement field names in a parsed checklist.
    Adds a 'canonical_field' key to each row.
    """
    result = []
    for req in requirements:
        raw = req.get("requirement", "")
        canonical = normalize_field_name(raw)
        result.append({**req, "canonical_field": canonical})
    return result


def normalize_eng_json(eng_json: dict) -> dict:
    """
    Walk the engineering JSON title_block and normalize any non-canonical keys.
    Returns a new dict with canonical keys in title_block.
    """
    import copy
    out = copy.deepcopy(eng_json)
    tb = out.get("title_block", {})
    normalized_tb = {}
    for k, v in tb.items():
        canonical = normalize_field_name(k)
        normalized_tb[canonical] = v
    out["title_block"] = normalized_tb
    return out
