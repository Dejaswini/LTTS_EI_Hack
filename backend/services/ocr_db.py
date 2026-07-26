# backend/services/ocr_db.py
# OCR Coordinate Database — stores every OCR detection with a unique ID.
# AI-extracted fields reference OCR IDs instead of duplicating coordinates.
# Highlight requests retrieve bbox from this DB — never re-run OCR.

from __future__ import annotations
import os, cv2
import numpy as np
from PIL import Image


# ── OCR DB Builder ────────────────────────────────────────────────────────────

def build_ocr_db(raw_detections: list[dict]) -> dict[str, dict]:
    """
    Convert raw OCR detections into a keyed coordinate database.
    Assigns unique IDs if not already set.

    Returns:
        { "TXT_0001": {id, text, bbox, confidence, page}, ... }
    """
    db = {}
    for i, det in enumerate(raw_detections):
        ocr_id = det.get("id") or f"TXT_{i:04d}"
        db[ocr_id] = {
            "id":         ocr_id,
            "text":       det.get("text", ""),
            "bbox":       det.get("bbox", []),
            "confidence": det.get("confidence", 0.0),
            "page":       det.get("page", 1),
            "type":       det.get("type", "ocr"),
        }
    return db


# ── Field Linker ──────────────────────────────────────────────────────────────

def link_fields_to_ocr(eng_json: dict, ocr_db: dict[str, dict]) -> dict:
    """
    Walk every extracted field in eng_json.
    For each scalar value, find the best matching OCR entry by text similarity.
    Attach ocr_id and bbox to the field so the frontend can highlight it.

    Returns an updated eng_json with ocr_id + bbox references added.
    """
    import copy
    result = copy.deepcopy(eng_json)
    _link_recursive(result, ocr_db)
    return result


def _link_recursive(obj, ocr_db: dict):
    """Recursively walk eng_json and attach ocr_id references."""
    if isinstance(obj, dict):
        # If this dict has a "value" key, try to link it
        if "value" in obj and isinstance(obj["value"], str):
            match = _find_best_match(obj["value"], ocr_db)
            if match:
                obj.setdefault("ocr_id", match["id"])
                obj.setdefault("bbox",   match["bbox"])
        for v in obj.values():
            _link_recursive(v, ocr_db)
    elif isinstance(obj, list):
        for item in obj:
            _link_recursive(item, ocr_db)


def _find_best_match(value: str, ocr_db: dict[str, dict]) -> dict | None:
    """Find the OCR entry whose text best matches the given value."""
    if not value or not value.strip():
        return None
    value_norm = value.strip().lower()
    # Exact match first
    for entry in ocr_db.values():
        if entry["text"].strip().lower() == value_norm:
            return entry
    # Substring match
    for entry in ocr_db.values():
        if value_norm in entry["text"].strip().lower() or \
           entry["text"].strip().lower() in value_norm:
            return entry
    return None


def get_bbox_for_ocr_id(ocr_id: str, ocr_db: dict) -> list[int]:
    """Return bbox for a given OCR ID from the database."""
    entry = ocr_db.get(ocr_id)
    return entry["bbox"] if entry else []


# ── Highlight Generator ───────────────────────────────────────────────────────

def generate_highlight(
    image_path: str,
    bbox: list[int],
    output_path: str | None = None,
    colour: tuple = (34, 197, 94),   # green (BGR)
    thickness: int = 3,
) -> str:
    """
    Draw a highlight rectangle on the image at the given bbox.
    NEVER re-runs OCR. Works purely from cached image + bbox.

    Args:
        image_path:  Path to the original (or annotated) cached drawing image.
        bbox:        [x1, y1, x2, y2] bounding box.
        output_path: Where to save the highlighted image.
                     Defaults to highlight_temp.png next to image.
        colour:      BGR colour tuple for rectangle. Default = green.
        thickness:   Rectangle border thickness in pixels. Default = 3.

    Returns:
        Absolute path to the highlighted image.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Image not found: {image_path}")

    if len(bbox) != 4:
        raise ValueError(f"Invalid bbox: {bbox}")

    x1, y1, x2, y2 = [int(b) for b in bbox]
    h, w = img.shape[:2]

    # Clamp to image bounds
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    # Draw filled semi-transparent highlight
    overlay = img.copy()
    # Convert green to RGBA-like semi-fill
    fill_colour = tuple(int(c * 0.25) for c in colour)  # dim fill
    cv2.rectangle(overlay, (x1, y1), (x2, y2), fill_colour, -1)
    cv2.addWeighted(overlay, 0.35, img, 0.65, 0, img)

    # Draw solid border
    cv2.rectangle(img, (x1, y1), (x2, y2), colour, thickness)

    # Draw corner tick marks for precision feel
    tick = min(20, (x2 - x1) // 4, (y2 - y1) // 4)
    for (sx, sy, dx, dy) in [
        (x1, y1, 1, 1), (x2, y1, -1, 1),
        (x1, y2, 1, -1), (x2, y2, -1, -1),
    ]:
        cv2.line(img, (sx, sy), (sx + dx * tick, sy), colour, thickness + 1)
        cv2.line(img, (sx, sy), (sx, sy + dy * tick), colour, thickness + 1)

    # Label above bbox
    label_text = f"[{x1},{y1}]→[{x2},{y2}]"
    (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    lx = max(0, x1)
    ly = max(th + 8, y1 - 5)
    cv2.rectangle(img, (lx, ly - th - 6), (lx + tw + 6, ly), colour, -1)
    cv2.putText(img, label_text, (lx + 3, ly - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (10, 10, 10), 1)

    # Save
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(image_path), "highlight_temp.png"
        )
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cv2.imwrite(output_path, img)
    return os.path.abspath(output_path)
