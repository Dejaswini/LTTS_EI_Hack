# backend/services/rule_engine.py
# Engineering Rule Engine — sits between AI extraction and checklist validation.
# Responsibilities:
#   1. Load company-specific rules
#   2. Normalize field names
#   3. Validate engineering format rules (dimensions, tolerances, revision, etc.)
#   4. Apply drawing-type rules (Part vs Assembly)
#   5. Apply company-specific rules
#   6. Generate Engineering Quality Score

from __future__ import annotations
import os, re, json
from services.field_mapper import normalize_eng_json, normalize_checklist, normalize_field_name

RULES_DIR = os.path.join(os.path.dirname(__file__), "..", "rules")

# ── Company mapping ───────────────────────────────────────────────────────────
COMPANY_FILE_MAP = {
    "ltts":         "LTTS.json",
    "bosch":        "Bosch.json",
    "tvs":          "TVS.json",
    "hyundai":      "Hyundai.json",
    "ashok leyland":"AshokLeyland.json",
    "custom company":"Custom.json",
    "custom":       "Custom.json",
}

# ── Engineering format patterns ───────────────────────────────────────────────
FORMAT_PATTERNS = {
    "dimension": [
        r"^\d+(\.\d+)?$",           # 120, 25.6
        r"^[ØøRr]\d+(\.\d+)?$",    # Ø20, R12
        r"^\d+°$",                  # 45°
        r"^[Mm]\d+[xX]\d+(\.\d+)?$",  # M10x1.5
        r"^\d+(\.\d+)?\s*[xX]\s*\d+(\.\d+)?$",  # 10x20
    ],
    "tolerance": [
        r"^[±]\s*\d+(\.\d+)?$",    # ±0.02
        r"^[Hh]\d+$",              # H7
        r"^[Gg]\d+$",              # g6
        r"^IT\d+$",                # IT7
        r"^[A-Za-z]\d+/[A-Za-z]\d+$",  # H7/g6
        r"^[±]\d+°$",              # ±1°
        r"^\d+(\.\d+)?/\d+(\.\d+)?$",  # 0.02/0.05
    ],
    "revision": [
        r"^[A-Z]$",                # A, B, C
        r"^[0-9]{1,3}$",           # 01, 02
        r"^[A-Z][0-9]$",           # A1, B2
    ],
    "drawing_number": [
        r"^[A-Z0-9][\w\-\.]{2,19}$",  # ABC-123, DWG-0098
    ],
    "date": [
        r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$",  # 10.07.2026
        r"^\d{4}[./\-]\d{1,2}[./\-]\d{1,2}$",     # 2026-07-10
    ],
    "scale": [
        r"^\d+:\d+$",             # 1:1, 1:2
        r"^\d+$",                  # 1
    ],
    "quantity": [
        r"^[1-9]\d*$",             # positive integer
    ],
}


# ── Rule loader ───────────────────────────────────────────────────────────────

def load_company_rules(company_name: str) -> dict:
    """Load company-specific rules JSON. Falls back to Custom if not found."""
    key = company_name.strip().lower()
    filename = COMPANY_FILE_MAP.get(key, "Custom.json")
    path = os.path.join(RULES_DIR, filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"required_fields": {"part": [], "assembly": []},
            "format_rules": {}, "custom_rules": {}}


# ── Format validator ──────────────────────────────────────────────────────────

def validate_format(field: str, value: str) -> tuple[bool, str]:
    """
    Check if a value matches known engineering format rules.
    Returns (is_valid, reason).
    """
    if not value or not str(value).strip():
        return False, "Empty value"

    patterns = FORMAT_PATTERNS.get(field, [])
    if not patterns:
        return True, "No format rule defined"

    v = str(value).strip()
    for pat in patterns:
        if re.match(pat, v, re.IGNORECASE):
            return True, "Valid format"

    return False, f"Invalid {field} format: '{v}'"


# ── Core Rule Engine ──────────────────────────────────────────────────────────

def run_rule_engine(
    eng_json: dict,
    drawing_type: str,
    company_name: str,
    checklist: list[dict] | None = None,
) -> dict:
    """
    Execute the full rule engine pipeline.

    Pipeline:
        1. Normalize field names
        2. Apply engineering logic rules (type-based)
        3. Apply format validation
        4. Apply company-specific rules
        5. Build final validation rows
        6. Compute quality score

    Returns:
        {
          "normalized_json":   dict,
          "validation_rows":   list of {requirement, expected, extracted, status, reason},
          "rule_violations":   list of str,
          "quality_score":     dict,
        }
    """
    # Step 1 — Normalize
    norm_json = normalize_eng_json(eng_json)

    # Step 2 — Load company rules
    company_rules = load_company_rules(company_name)
    required_for_type = company_rules.get("required_fields", {}).get(drawing_type, [])

    # Step 3 — Engineering logic rules
    logic_violations = _check_logic_rules(norm_json, drawing_type)

    # Step 4 — Format validation
    format_rows, format_violations = _check_formats(norm_json)

    # Step 5 — Required field validation (company rules)
    required_rows = _check_required_fields(norm_json, required_for_type, drawing_type)

    # Step 6 — Checklist validation (if provided)
    checklist_rows = []
    if checklist:
        norm_checklist = normalize_checklist(checklist)
        checklist_rows = _check_checklist(norm_json, norm_checklist, drawing_type)

    # Step 7 — Company custom rules
    custom_rows = _check_custom_rules(norm_json, drawing_type,
                                      company_rules.get("custom_rules", {}))

    # Merge all rows (priority: logic > format > required > custom > checklist)
    all_rows = required_rows + format_rows + custom_rows + checklist_rows

    # Deduplicate by requirement name
    seen = set()
    deduped = []
    for row in all_rows:
        key = row["requirement"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    # Quality score
    quality = _compute_quality_score(norm_json, eng_json.get("_ocr_meta", {}),
                                     deduped, logic_violations + format_violations)

    return {
        "normalized_json":  norm_json,
        "validation_rows":  deduped,
        "rule_violations":  logic_violations + format_violations,
        "quality_score":    quality,
    }


# ── Engineering logic rules ───────────────────────────────────────────────────

def _check_logic_rules(norm_json: dict, drawing_type: str) -> list[str]:
    """Apply the 10 engineering logic rules. Returns list of violation strings."""
    violations = []
    tb = norm_json.get("title_block", {})

    # Rule 1 — Assembly must have BOM
    if drawing_type == "assembly":
        bom = norm_json.get("bill_of_materials", [])
        if not bom:
            violations.append("Rule 1: Assembly drawing must contain a Bill of Materials.")

    # Rule 2 — Part must have dimensions
    if drawing_type == "part":
        dims = norm_json.get("dimensions", [])
        if not dims:
            violations.append("Rule 2: Part drawing must contain dimensions.")

    # Rule 3 — Part must have material
    if drawing_type == "part":
        mat = norm_json.get("material", "")
        if not mat:
            violations.append("Rule 3: Part drawing must specify material.")

    # Rule 4 — Assembly material should be NA
    # (informational only — no violation raised)

    # Rule 7 — Revision appears only once (check for duplicates in OCR)
    # Handled by extraction — just validate presence
    rev = _get_val(tb.get("revision"))
    if rev and len(rev) > 10:
        violations.append("Rule 7: Revision value appears unusually long — may be duplicated.")

    # Rule 9 — BOM item numbers unique
    bom = norm_json.get("bill_of_materials", [])
    if bom:
        item_nos = []
        for row in bom:
            if isinstance(row, dict):
                v = _get_val(row.get("item_no") or row.get("item", ""))
                if v:
                    item_nos.append(v)
        if len(item_nos) != len(set(item_nos)):
            violations.append("Rule 9: BOM item numbers are not unique.")

    # Rule 10 — BOM quantity positive
    if bom:
        for i, row in enumerate(bom):
            if isinstance(row, dict):
                qty = _get_val(row.get("quantity", ""))
                if qty:
                    try:
                        if int(str(qty).strip()) <= 0:
                            violations.append(
                                f"Rule 10: BOM row {i+1} quantity must be > 0 (got '{qty}').")
                    except (ValueError, TypeError):
                        pass

    return violations


# ── Format validation rows ────────────────────────────────────────────────────

def _check_formats(norm_json: dict) -> tuple[list[dict], list[str]]:
    """Check format of key fields. Returns (rows, violations)."""
    rows, violations = [], []
    tb = norm_json.get("title_block", {})

    format_checks = [
        ("Revision",        "revision",        _get_val(tb.get("revision"))),
        ("Drawing Number",  "drawing_number",  _get_val(tb.get("drawing_number"))),
        ("Scale",           "scale",           _get_val(tb.get("scale"))),
        ("Date",            "date",            _get_val(tb.get("date"))),
    ]

    for label, field, value in format_checks:
        if not value:
            continue  # skip — presence check handled by required fields
        valid, reason = validate_format(field, value)
        rows.append({
            "requirement": f"{label} Format",
            "expected":    "Valid engineering format",
            "extracted":   value,
            "status":      "✓" if valid else "✗",
            "reason":      "Valid format" if valid else reason,
        })
        if not valid:
            violations.append(f"Format: {label} — {reason}")

    # Validate dimension formats
    dims = norm_json.get("dimensions", [])
    invalid_dims = []
    for d in dims:
        v = d if isinstance(d, str) else _get_val(d)
        if v:
            ok, _ = validate_format("dimension", v)
            if not ok:
                invalid_dims.append(v)
    if invalid_dims:
        rows.append({
            "requirement": "Dimension Format",
            "expected":    "Valid dimension format (e.g. 120, Ø20, R12)",
            "extracted":   f"{len(invalid_dims)} invalid: {', '.join(invalid_dims[:3])}",
            "status":      "✗",
            "reason":      "One or more dimensions have invalid format.",
        })

    return rows, violations


# ── Required field rows ───────────────────────────────────────────────────────

def _check_required_fields(norm_json: dict, required: list[str],
                            drawing_type: str) -> list[dict]:
    """Build validation rows for each required field from company rules."""
    rows = []
    tb = norm_json.get("title_block", {})

    # Parts-only fields — mark NA for assembly
    PART_ONLY = {"material", "surface_finish", "dimensions", "tolerances",
                 "projection_method", "gdt_symbols", "threads"}
    ASSEMBLY_ONLY = {"bill_of_materials"}

    all_fields = list(dict.fromkeys(required))  # preserve order, dedupe

    for field in all_fields:
        label = field.replace("_", " ").title()

        # NA logic
        if drawing_type == "assembly" and field in PART_ONLY:
            rows.append({"requirement": label, "expected": "Required",
                         "extracted": "N/A", "status": "NA",
                         "reason": "Not applicable for Assembly drawing."})
            continue
        if drawing_type == "part" and field in ASSEMBLY_ONLY:
            rows.append({"requirement": label, "expected": "Required",
                         "extracted": "N/A", "status": "NA",
                         "reason": "Not applicable for Part drawing."})
            continue

        # Get value
        extracted = _get_field_value(norm_json, field)
        if extracted:
            rows.append({"requirement": label, "expected": "Required",
                         "extracted": extracted, "status": "✓", "reason": "Found"})
        else:
            rows.append({"requirement": label, "expected": "Required",
                         "extracted": "Missing", "status": "✗",
                         "reason": "Missing from drawing."})
    return rows


# ── Checklist rows ────────────────────────────────────────────────────────────

def _check_checklist(norm_json: dict, norm_checklist: list[dict],
                     drawing_type: str) -> list[dict]:
    """Execute checklist validation using normalized field names."""
    rows = []
    PART_ONLY  = {"material","surface_finish","dimensions","tolerances","projection_method"}
    ASSY_ONLY  = {"bill_of_materials"}

    for item in norm_checklist:
        req       = item.get("requirement", "")
        canonical = item.get("canonical_field", "")
        expected  = item.get("expected", "Required")
        notes     = item.get("notes", "")

        # NA check
        if expected.lower() in ("n/a", "na", "not applicable"):
            rows.append({"requirement": req, "expected": expected,
                         "extracted": "N/A", "status": "NA",
                         "reason": "Marked N/A in checklist."})
            continue
        if drawing_type == "assembly" and canonical in PART_ONLY:
            rows.append({"requirement": req, "expected": expected,
                         "extracted": "N/A", "status": "NA",
                         "reason": "Not applicable for Assembly drawing."})
            continue
        if drawing_type == "part" and canonical in ASSY_ONLY:
            rows.append({"requirement": req, "expected": expected,
                         "extracted": "N/A", "status": "NA",
                         "reason": "Not applicable for Part drawing."})
            continue

        extracted = _get_field_value(norm_json, canonical)
        if extracted:
            rows.append({"requirement": req, "expected": expected,
                         "extracted": extracted, "status": "✓", "reason": "Found"})
        else:
            rows.append({"requirement": req, "expected": expected,
                         "extracted": "Missing", "status": "✗",
                         "reason": f"'{req}' missing from drawing."})
    return rows


# ── Custom rule rows ──────────────────────────────────────────────────────────

def _check_custom_rules(norm_json: dict, drawing_type: str,
                        custom_rules: dict) -> list[dict]:
    rows = []
    if custom_rules.get("surface_finish_mandatory") and drawing_type == "part":
        sf = norm_json.get("surface_finish", [])
        rows.append({
            "requirement": "Surface Finish (Company Mandatory)",
            "expected":    "Required by company rules",
            "extracted":   f"{len(sf)} found" if sf else "Missing",
            "status":      "✓" if sf else "✗",
            "reason":      "Found" if sf else "Surface finish mandatory per company rules.",
        })
    if custom_rules.get("heat_treatment_required") and drawing_type == "part":
        # Look in notes/other_annotations
        notes = " ".join(norm_json.get("notes", []) + norm_json.get("general_notes", []))
        found = "heat" in notes.lower() or "treatment" in notes.lower()
        rows.append({
            "requirement": "Heat Treatment (Company Mandatory)",
            "expected":    "Mentioned in notes",
            "extracted":   "Found" if found else "Missing",
            "status":      "✓" if found else "✗",
            "reason":      "Found in notes" if found else "Heat treatment not mentioned.",
        })
    return rows


# ── Quality Score ─────────────────────────────────────────────────────────────

def _compute_quality_score(norm_json: dict, ocr_meta: dict,
                            val_rows: list[dict],
                            violations: list[str]) -> dict:
    """Generate the Engineering Quality Score."""
    # OCR accuracy — average confidence of OCR detections
    ocr_confidences = ocr_meta.get("confidences", [])
    ocr_accuracy = round(sum(ocr_confidences) / len(ocr_confidences) * 100, 1) \
                   if ocr_confidences else 0.0

    # Checklist compliance
    applicable = [r for r in val_rows if r.get("status") != "NA"]
    passed     = sum(1 for r in applicable if r.get("status") == "✓")
    failed     = sum(1 for r in applicable if r.get("status") == "✗")
    na_count   = sum(1 for r in val_rows if r.get("status") == "NA")
    compliance = round(passed / len(applicable) * 100, 1) if applicable else 0.0

    # Extraction accuracy — fields found vs total required
    tb = norm_json.get("title_block", {})
    extracted_fields = sum(1 for v in tb.values() if _get_val(v))
    total_tb = max(len(tb), 1)
    extraction_accuracy = round(extracted_fields / total_tb * 100, 1)

    # Overall score (weighted)
    if ocr_accuracy > 0:
        overall = round(ocr_accuracy * 0.2 + extraction_accuracy * 0.3 + compliance * 0.5, 1)
    else:
        overall = round(extraction_accuracy * 0.4 + compliance * 0.6, 1)

    warnings = [v for v in violations if "Rule" not in v]

    return {
        "overall_score":        overall,
        "ocr_accuracy":         ocr_accuracy,
        "extraction_accuracy":  extraction_accuracy,
        "checklist_compliance": compliance,
        "passed":               passed,
        "failed":               failed,
        "na":                   na_count,
        "missing_fields":       failed,
        "validation_failures":  failed,
        "warnings":             len(warnings),
        "rule_violations":      len(violations),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_val(v) -> str:
    if v is None: return ""
    if isinstance(v, dict): return str(v.get("value", ""))
    return str(v).strip()


def _get_field_value(norm_json: dict, field: str) -> str:
    """Get a canonical field value from normalized eng_json."""
    tb = norm_json.get("title_block", {})
    # Check title_block first
    if field in tb:
        return _get_val(tb[field])
    # Check top-level
    val = norm_json.get(field)
    if val is None:
        return ""
    if isinstance(val, list):
        return f"{len(val)} found" if val else ""
    return _get_val(val)
