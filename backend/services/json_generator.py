# backend/services/json_generator.py
# Builds and persists the final structured JSON for a processed drawing.

from __future__ import annotations
import json
import os
from datetime import datetime

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def generate_json(
    drawing_type: str,
    parsed_data: dict,
    original_filename: str,
    raw_detections: list[dict],
) -> tuple[dict, str]:
    """
    Assemble the final output JSON and save it to the output/ directory.

    Args:
        drawing_type:      "part" or "assembly"
        parsed_data:       Output from part_parser or assembly_parser
        original_filename: The uploaded file's name (used to name the output)
        raw_detections:    All raw OCR detections (stored for traceability)

    Returns:
        (output_dict, saved_filename) — the dict and the filename it was saved as.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Build top-level envelope
    output = {
        "meta": {
            "source_file":    original_filename,
            "drawing_type":   drawing_type,
            "processed_at":   datetime.utcnow().isoformat() + "Z",
            "total_ocr_hits": len(raw_detections),
        },
        "drawing_type": drawing_type,
        "extracted_data": parsed_data,
        "raw_ocr": raw_detections,
    }

    # Save to output/{stem}_{type}_output.json
    stem = os.path.splitext(original_filename)[0]
    filename = f"{stem}_{drawing_type}_output.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output, filename


def load_result(filename: str) -> dict | None:
    """Load a previously saved result JSON by filename.  Returns None if not found."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
