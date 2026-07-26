# backend/services/classifier.py
# Keyword-based drawing classifier.
# Scores the OCR text against two keyword sets and returns the best match.

from __future__ import annotations

# ---------------------------------------------------------------------------
# Keyword sets (all uppercase for case-insensitive matching)
# ---------------------------------------------------------------------------

ASSEMBLY_KEYWORDS: list[str] = [
    "BILL OF MATERIAL",
    "BILL OF MATERIALS",
    "BOM",
    "ITEM NO",
    "ITEM NO.",
    "ITEM NUMBER",
    "PART NUMBER",
    "PART NO",
    "PART NO.",
    "QTY",
    "QUANTITY",
    "ASSEMBLY",
    "ITEM",
]

PART_KEYWORDS: list[str] = [
    "DRAWING TITLE",
    "TITLE",
    "DRAWING NUMBER",
    "DWG NO",
    "DWG. NO",
    "DIMENSION",
    "TOLERANCE",
    "DRAWN BY",
    "CHECKED BY",
    "DESIGNED BY",
    "SCALE",
    "REVISION",
    "REV",
    "MATERIAL",
    "WEIGHT",
    "SHEET",
    "SIZE",
]


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def classify_drawing(detections: list[dict]) -> str:
    """
    Examine OCR detections and return 'assembly' or 'part'.

    Strategy
    --------
    Each detection text is compared against both keyword lists.
    A keyword is considered matched when the keyword string appears
    as a substring of the (uppercased) OCR text.
    The class with the higher cumulative match count wins.

    Returns:
        "assembly" | "part"
    """
    # Collect all detected text in uppercase for uniform comparison
    all_text = " ".join(d["text"].upper() for d in detections)

    assembly_score = _score(all_text, ASSEMBLY_KEYWORDS)
    part_score = _score(all_text, PART_KEYWORDS)

    # Prefer 'assembly' on a tie because BOM presence is a stronger signal
    if assembly_score >= part_score and assembly_score > 0:
        return "assembly"
    return "part"


def _score(text: str, keywords: list[str]) -> int:
    """Count how many keywords appear in the given text."""
    return sum(1 for kw in keywords if kw in text)
