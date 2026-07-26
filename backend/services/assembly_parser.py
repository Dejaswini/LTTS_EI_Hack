# backend/services/assembly_parser.py
# Extracts structured fields from Assembly Drawing OCR detections.
#
# Strategy
# --------
# 1. Find the BOM header row (contains ITEM NO / PART NUMBER / QTY headers).
# 2. All detections below the header row are treated as BOM data rows.
# 3. Rows are grouped by Y-coordinate proximity (same horizontal band = same row).
# 4. Within each row band, detections are sorted left-to-right and mapped to
#    columns based on their X centre relative to the header column centres.

from __future__ import annotations
import re

# ---------------------------------------------------------------------------
# Label constants
# ---------------------------------------------------------------------------

HEADER_KEYWORDS: list[str] = [
    "ITEM NO", "ITEM NO.", "ITEM NUMBER", "ITEM",
    "PART NUMBER", "PART NO", "PART NO.",
    "QTY", "QUANTITY",
]

TITLE_LABELS    = ["TITLE:", "TITLE", "DRAWING TITLE"]
REVISION_LABELS = ["REVISION", "REV", "REV."]
DATE_LABELS     = ["DATE"]
DWG_NO_LABELS   = ["DWG. NO", "DWG.NO", "DWG NO", "DRAWING NUMBER"]

# Regex: detect a pure integer string (item numbers)
_INT_RE = re.compile(r"^\d+$")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def parse_assembly_drawing(detections: list[dict]) -> dict:
    """
    Extract all Assembly Drawing fields from OCR detections.

    Returns a dict with:
        title, revision, date, drawing_number  — field dicts
        bill_of_materials                       — list of BOM row dicts
    """
    result: dict = {}

    # --- Header / meta fields -----------------------------------------------
    result["title"]          = _find_label_value(detections, TITLE_LABELS)
    result["revision"]       = _find_label_value(detections, REVISION_LABELS)
    result["date"]           = _find_label_value(detections, DATE_LABELS)
    result["drawing_number"] = _find_label_value(detections, DWG_NO_LABELS)

    # --- Bill of Materials ---------------------------------------------------
    result["bill_of_materials"] = _extract_bom(detections)

    return result


# ---------------------------------------------------------------------------
# BOM extraction
# ---------------------------------------------------------------------------

def _extract_bom(detections: list[dict]) -> list[dict]:
    """
    Locate the BOM header row, identify column centres, then group all
    detections below the header into rows by Y-band.
    """
    # Step 1: Find the detection that anchors each BOM column header
    item_header   = _find_detection(detections, ["ITEM NO", "ITEM NO.", "ITEM", "ITEM NUMBER"])
    partno_header = _find_detection(detections, ["PART NUMBER", "PART NO", "PART NO."])
    qty_header    = _find_detection(detections, ["QTY", "QUANTITY"])

    if not any([item_header, partno_header, qty_header]):
        return []  # No BOM found

    # Step 2: Determine the Y-coordinate of the header row (lowest header bottom)
    header_y_max = max(
        h["bbox"][3] for h in [item_header, partno_header, qty_header] if h
    )

    # Step 3: Compute column X-centre boundaries for assignment
    col_centres: dict[str, float] = {}
    if item_header:
        x1, _, x2, _ = item_header["bbox"]
        col_centres["item"] = (x1 + x2) / 2
    if partno_header:
        x1, _, x2, _ = partno_header["bbox"]
        col_centres["part_number"] = (x1 + x2) / 2
    if qty_header:
        x1, _, x2, _ = qty_header["bbox"]
        col_centres["quantity"] = (x1 + x2) / 2

    # Step 4: Collect all detections below the header row
    below = [
        d for d in detections
        if d["bbox"][1] > header_y_max  # top of detection is below header
    ]

    if not below:
        return []

    # Step 5: Group detections into horizontal bands (same row ≈ within 15 px)
    rows = _group_into_rows(below, tolerance_px=15)

    # Step 6: Map each row's detections to column names and build BOM entries
    bom = []
    for row_dets in rows:
        entry = _map_row_to_columns(row_dets, col_centres)
        # Only keep rows that have at least item or part_number
        if entry.get("item") or entry.get("part_number"):
            bom.append(entry)

    return bom


def _group_into_rows(detections: list[dict], tolerance_px: int = 15) -> list[list[dict]]:
    """
    Group detections by Y-centre proximity into horizontal bands.
    Returns a list of groups, each sorted by X-centre.
    """
    sorted_dets = sorted(detections, key=lambda d: (d["bbox"][1] + d["bbox"][3]) / 2)

    groups: list[list[dict]] = []
    current_group: list[dict] = []
    prev_cy: float | None = None

    for det in sorted_dets:
        cy = (det["bbox"][1] + det["bbox"][3]) / 2
        if prev_cy is None or abs(cy - prev_cy) <= tolerance_px:
            current_group.append(det)
        else:
            if current_group:
                groups.append(sorted(current_group, key=lambda d: d["bbox"][0]))
            current_group = [det]
        prev_cy = cy

    if current_group:
        groups.append(sorted(current_group, key=lambda d: d["bbox"][0]))

    return groups


def _map_row_to_columns(
    row_dets: list[dict],
    col_centres: dict[str, float],
) -> dict:
    """
    For each detection in the row, assign it to the nearest column centre and
    build a {column_name: {value, bbox, confidence}} dict.
    """
    entry: dict = {}
    col_names = list(col_centres.keys())
    col_xs    = list(col_centres.values())

    for det in row_dets:
        det_cx = (det["bbox"][0] + det["bbox"][2]) / 2
        # Find the closest column
        dists = [abs(det_cx - cx) for cx in col_xs]
        nearest_col = col_names[dists.index(min(dists))]

        # Keep only the first match per column (highest confidence wins)
        if nearest_col not in entry:
            entry[nearest_col] = {
                "value": det["text"],
                "bbox": det["bbox"],
                "confidence": det["confidence"],
            }

    return entry


# ---------------------------------------------------------------------------
# Generic label-value lookup (same logic as part_parser but simpler)
# ---------------------------------------------------------------------------

def _find_detection(detections: list[dict], label_variants: list[str]) -> dict | None:
    """Return the first detection whose text contains any label variant."""
    for det in detections:
        upper = det["text"].upper().strip()
        if any(lv.upper() in upper for lv in label_variants):
            return det
    return None


def _find_label_value(
    detections: list[dict],
    label_variants: list[str],
    proximity_px: int = 400,
) -> dict | None:
    """
    Find a label detection then return the nearest value to its right.
    """
    label_det = _find_detection(detections, label_variants)
    if label_det is None:
        return None

    lx1, ly1, lx2, ly2 = label_det["bbox"]
    label_cy = (ly1 + ly2) / 2

    best: dict | None = None
    best_dist = float("inf")

    for det in detections:
        if det is label_det:
            continue
        dx1, dy1, dx2, dy2 = det["bbox"]
        det_cx = (dx1 + dx2) / 2
        det_cy = (dy1 + dy2) / 2

        # Value should be to the right and on the same horizontal band
        if det_cx > lx2 and abs(det_cy - label_cy) < proximity_px:
            dist = (det_cx - lx2) + abs(det_cy - label_cy) * 0.5
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
