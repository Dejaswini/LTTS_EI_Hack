# backend/services/part_parser.py
# Extracts structured fields from Part Drawing OCR detections.
#
# Strategy
# --------
# For each target field we look for a "label" detection whose text closely
# matches known label strings.  Once the label is found, we look for the
# nearest detection to the right or below it (within a generous pixel
# threshold) and treat that as the value.
#
# Dimensions and tolerances are extracted with a regex pass over all text.

from __future__ import annotations
import re

# ---------------------------------------------------------------------------
# Label → canonical field name mapping
# ---------------------------------------------------------------------------
FIELD_LABELS: dict[str, list[str]] = {
    "drawing_title":   ["DRAWING TITLE", "TITLE"],
    "drawing_number":  ["DRAWING NUMBER", "DWG NO", "DWG. NO", "DWG.NO"],
    "revision":        ["REVISION", "REV"],
    "scale":           ["SCALE"],
    "date":            ["DATE"],
    "drawn_by":        ["DRAWN BY"],
    "checked_by":      ["CHECKED BY"],
    "designed_by":     ["DESIGNED BY"],
    "material":        ["MATERIAL"],
    "weight":          ["WEIGHT", "WEIGHT(KG)"],
    "sheet":           ["SHEET"],
}

# Regex patterns for numeric dimension / tolerance values
DIMENSION_PATTERN = re.compile(
    r"(?:Ø|ø|R|φ)?\s*\d+(?:[.,]\d+)?(?:\s*[xX±]\s*\d+(?:[.,]\d+)?)*"
)
TOLERANCE_PATTERN = re.compile(r"[±]\s*\d+(?:[.,]\d+)?")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def parse_part_drawing(detections: list[dict]) -> dict:
    """
    Extract all Part Drawing fields from OCR detections.

    Returns a dict with keys for every standard field plus
    'dimensions' (list) and 'tolerances' (list).
    """
    result: dict = {}

    # --- Extract labelled fields -------------------------------------------
    for field, labels in FIELD_LABELS.items():
        match = _find_labelled_value(detections, labels)
        if match:
            result[field] = match

    # --- Extract dimensions (list) -----------------------------------------
    result["dimensions"] = _extract_pattern_list(detections, DIMENSION_PATTERN)

    # --- Extract tolerances (list) -----------------------------------------
    result["tolerances"] = _extract_pattern_list(detections, TOLERANCE_PATTERN)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_labelled_value(
    detections: list[dict],
    label_variants: list[str],
    proximity_px: int = 300,
) -> dict | None:
    """
    Find a detection whose text matches one of the label_variants, then
    return the nearest detection to its right or below as the value.

    Returns a field dict: {value, bbox, confidence} or None if not found.
    """
    label_det = None
    for det in detections:
        upper = det["text"].upper().strip()
        if any(lv in upper for lv in label_variants):
            label_det = det
            break

    if label_det is None:
        return None

    lx1, ly1, lx2, ly2 = label_det["bbox"]
    label_cx = (lx1 + lx2) / 2
    label_cy = (ly1 + ly2) / 2

    best: dict | None = None
    best_dist = float("inf")

    for det in detections:
        if det is label_det:
            continue
        # Skip other labels
        upper = det["text"].upper().strip()
        if any(lv in upper for lv in [v for vlist in FIELD_LABELS.values() for v in vlist]):
            continue

        dx1, dy1, dx2, dy2 = det["bbox"]
        det_cx = (dx1 + dx2) / 2
        det_cy = (dy1 + dy2) / 2

        # Value should be to the right or slightly below the label
        if det_cx > lx1 and abs(det_cy - label_cy) < proximity_px:
            dist = abs(det_cx - lx2) + abs(det_cy - label_cy) * 0.5
            if dist < best_dist:
                best_dist = dist
                best = det

    if best is None:
        return None

    return {
        "value": best["text"],
        "bbox": best["bbox"],
        "confidence": best["confidence"],
    }


def _extract_pattern_list(detections: list[dict], pattern: re.Pattern) -> list[dict]:
    """
    Find all OCR detections whose text matches the given regex pattern and
    return them as a list of {value, bbox, confidence} dicts.
    """
    found = []
    seen = set()

    for det in detections:
        matches = pattern.findall(det["text"])
        for m in matches:
            m_clean = m.strip()
            if m_clean and m_clean not in seen:
                seen.add(m_clean)
                found.append({
                    "value": m_clean,
                    "bbox": det["bbox"],
                    "confidence": det["confidence"],
                })

    return found
