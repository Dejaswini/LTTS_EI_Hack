# backend/services/annotator.py
# Draws coloured bounding boxes and labels on drawing images using OpenCV.

from __future__ import annotations
import os, cv2
import numpy as np
from PIL import Image

# Colour map per validation status (BGR for OpenCV)
STATUS_COLOUR = {
    "✓":  (34, 197, 94),    # green
    "✗":  (239, 68, 68),    # red
    "NA": (148, 163, 184),  # grey
    "ocr": (99, 102, 241),  # indigo for plain OCR boxes
}
LABEL_COLOUR = (255, 255, 255)  # white text


def annotate_drawing(
    image_path: str,
    ocr_results: list[dict],
    validation_rows: list[dict] | None = None,
    eng_json: dict | None = None,
) -> str:
    """
    Draw bounding boxes on the drawing image.

    Args:
        image_path:      Path to the source PNG.
        ocr_results:     List of {id, text, bbox, confidence, type}.
        validation_rows: Optional list of {requirement, status, bbox}.
        eng_json:        Optional structured engineering JSON.

    Returns:
        Path to the annotated image saved as annotated.png next to source.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    h, w = img.shape[:2]
    overlay = img.copy()

    # ── Draw OCR boxes (light) ───────────────────────────────────────────────
    for det in ocr_results:
        bbox = det.get("bbox", [])
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [int(b) for b in bbox]
        colour = STATUS_COLOUR["ocr"]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), colour, 1)

    # ── Draw validated / AI-extracted fields (thicker, labelled) ────────────
    if eng_json:
        _draw_eng_fields(overlay, eng_json, w, h)

    # Blend overlay with original
    cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)

    # ── Draw validation status labels ────────────────────────────────────────
    if validation_rows:
        _draw_validation_legend(img, validation_rows)

    out_dir = os.path.dirname(image_path)
    out_path = os.path.join(out_dir, "..", "annotated", "annotated.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, img)
    return os.path.abspath(out_path)


def _draw_eng_fields(img: np.ndarray, eng_json: dict, w: int, h: int):
    """Draw boxes around AI-identified engineering fields."""
    colour_map = {
        "drawing_title":  (251, 191, 36),    # yellow
        "drawing_number": (59, 130, 246),    # blue
        "revision":       (168, 85, 247),    # purple
        "scale":          (20, 184, 166),    # teal
        "material":       (249, 115, 22),    # orange
        "dimensions":     (34, 197, 94),     # green
        "tolerances":     (239, 68, 68),     # red
        "surface_finish": (99, 102, 241),    # indigo
        "threads":        (236, 72, 153),    # pink
    }
    def _draw_field(bbox, label, colour):
        if not bbox or len(bbox) != 4:
            return
        x1, y1, x2, y2 = [int(b) for b in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        cv2.rectangle(img, (x1, y1), (x2, y2), colour, 2)
        # Label background
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 4, y1), colour, -1)
        cv2.putText(img, label, (x1 + 2, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    for field, colour in colour_map.items():
        val = eng_json.get(field)
        if not val:
            continue
        if isinstance(val, dict) and "bbox" in val:
            _draw_field(val["bbox"], field.replace("_", " ").upper(), colour)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict) and "bbox" in item:
                    text = item.get("value", field)
                    _draw_field(item["bbox"], str(text)[:15], colour)

    # BOM
    bom = eng_json.get("bill_of_materials", [])
    for row in bom:
        if isinstance(row, dict):
            pn = row.get("part_number", {})
            if isinstance(pn, dict) and "bbox" in pn:
                _draw_field(pn["bbox"], f"BOM:{pn.get('value','')[:10]}", (56, 189, 248))


def _draw_validation_legend(img: np.ndarray, validation_rows: list[dict]):
    """Draw a small legend in the bottom-right corner."""
    counts = {"✓": 0, "✗": 0, "NA": 0}
    for r in validation_rows:
        s = r.get("status", "NA")
        if s in counts:
            counts[s] += 1
    h, w = img.shape[:2]
    x, y = w - 200, h - 80
    cv2.rectangle(img, (x - 5, y - 20), (w - 5, h - 5), (30, 30, 30), -1)
    for i, (s, c) in enumerate(STATUS_COLOUR.items()):
        if s == "ocr":
            continue
        label = f"{s}: {counts.get(s, 0)}"
        cv2.putText(img, label, (x, y + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1)
