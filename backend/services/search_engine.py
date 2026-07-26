# backend/services/search_engine.py
# Builds and queries a per-drawing search index from OCR + eng_json.

from __future__ import annotations
import re


def build_index(ocr_results: list[dict], eng_json: dict) -> dict:
    """
    Build a keyword → [{field_id, text, bbox, type, source}] index.
    Called after OCR + AI extraction complete for a drawing.
    """
    index: dict[str, list[dict]] = {}

    # ── OCR detections ────────────────────────────────────────────────────────
    for det in ocr_results:
        text = det.get("text", "").strip()
        if not text:
            continue
        _add_to_index(index, text, {
            "field_id":  det.get("id", ""),
            "text":      text,
            "bbox":      det.get("bbox", []),
            "type":      det.get("type", "ocr"),
            "source":    "ocr",
            "confidence": det.get("confidence", 0),
        })

    # ── AI-extracted fields ───────────────────────────────────────────────────
    tb = eng_json.get("title_block", {})
    for field, val in tb.items():
        if isinstance(val, str) and val:
            _add_to_index(index, val, {
                "field_id": field, "text": val,
                "bbox": [], "type": "title_block", "source": "ai",
            })

    for list_field in ["dimensions", "tolerances", "surface_finish",
                        "threads", "notes", "general_notes", "gdt_symbols"]:
        for i, item in enumerate(eng_json.get(list_field, [])):
            text = item if isinstance(item, str) else str(item)
            _add_to_index(index, text, {
                "field_id": f"{list_field}_{i}", "text": text,
                "bbox": [], "type": list_field, "source": "ai",
            })

    # ── BOM ───────────────────────────────────────────────────────────────────
    for i, row in enumerate(eng_json.get("bill_of_materials", [])):
        if isinstance(row, dict):
            for col in ["item_no", "part_number", "quantity", "description"]:
                val = row.get(col, "")
                if isinstance(val, dict):
                    val = val.get("value", "")
                if val:
                    _add_to_index(index, str(val), {
                        "field_id": f"bom_{i}_{col}",
                        "text": str(val),
                        "bbox": row.get(col, {}).get("bbox", []) if isinstance(row.get(col), dict) else [],
                        "type": "bom", "source": "ai",
                    })

    return index


def _add_to_index(index: dict, text: str, entry: dict):
    """Tokenise text and add entry under each token."""
    # Add full text
    key = text.lower().strip()
    index.setdefault(key, []).append(entry)
    # Add individual tokens (words / numbers)
    for token in re.split(r"[\s,;|/\\]+", text):
        t = token.lower().strip("()[]{}.")
        if len(t) >= 2:
            index.setdefault(t, []).append(entry)


def search(index: dict, query: str, max_results: int = 20) -> list[dict]:
    """
    Search the index for the query string.
    Returns deduplicated list of matching entries sorted by relevance.
    """
    q = query.lower().strip()
    seen = set()
    results = []

    # Exact key match first
    for entry in index.get(q, []):
        key = entry.get("field_id", "") + entry.get("text", "")
        if key not in seen:
            seen.add(key)
            results.append({**entry, "match_type": "exact"})

    # Substring match
    for k, entries in index.items():
        if q in k and k != q:
            for entry in entries:
                key = entry.get("field_id", "") + entry.get("text", "")
                if key not in seen:
                    seen.add(key)
                    results.append({**entry, "match_type": "partial"})

    return results[:max_results]
