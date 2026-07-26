# backend/services/ocr_service.py
# Handles all OCR-related operations compatible with PaddleOCR 2.8.1 / PaddleX backend.
#
# PaddleOCR 2.8.1 changed its internal API significantly:
#   - .ocr() now wraps .predict() and no longer accepts `cls=` kwarg
#   - Results are paddlex OCRResult dict-like objects, not plain lists
#   - Use keys: rec_texts, rec_scores, rec_polys / rec_boxes

import os
import fitz          # PyMuPDF
import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

# ---------------------------------------------------------------------------
# Shared PaddleOCR instance (lazy-loaded once per process)
# ---------------------------------------------------------------------------
_ocr_engine: PaddleOCR | None = None


def get_ocr_engine() -> PaddleOCR:
    """Lazy-initialise and return the shared PaddleOCR 2.8.1 instance."""
    global _ocr_engine
    if _ocr_engine is None:
        # NOTE: use_angle_cls is deprecated in 2.8.1 (use use_textline_orientation)
        # but still accepted; cls= kwarg on .ocr() is NO LONGER supported.
        _ocr_engine = PaddleOCR(lang="en")
    return _ocr_engine


# ---------------------------------------------------------------------------
# PDF → image conversion
# ---------------------------------------------------------------------------
def pdf_to_images(pdf_path: str, dpi: int = 200) -> list[np.ndarray]:
    """
    Convert every page of a PDF to an RGB numpy array using PyMuPDF (fitz).

    Args:
        pdf_path: Absolute path to the PDF file.
        dpi:      Render resolution (200 dpi balances quality vs speed).

    Returns:
        List of numpy uint8 arrays, shape (H, W, 3), one per page.
    """
    doc = fitz.open(pdf_path)
    zoom = dpi / 72          # 72 pt/inch is the PDF baseline
    matrix = fitz.Matrix(zoom, zoom)
    images = []

    for page in doc:
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        pil_img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        images.append(np.array(pil_img))

    doc.close()
    return images


# ---------------------------------------------------------------------------
# Single-image OCR  (PaddleOCR 2.8.1 compatible)
# ---------------------------------------------------------------------------
def run_ocr_on_image(image: np.ndarray) -> list[dict]:
    """
    Run PaddleOCR on a single numpy image (RGB, uint8).

    PaddleOCR 2.8.1 result format:
        result[0] is a paddlex OCRResult (dict-like) with keys:
            rec_texts   : list[str]
            rec_scores  : list[float]
            rec_boxes   : ndarray shape (N, 4)  [x1, y1, x2, y2]
            rec_polys   : list of polygon arrays (4-point)

    Returns:
        List of dicts: {text, confidence, bbox: [x1, y1, x2, y2]}
    """
    engine = get_ocr_engine()

    # Call without any extra kwargs — 2.8.1 does not accept cls=
    raw = engine.ocr(image)

    detections: list[dict] = []

    if not raw:
        return detections

    # raw is a list with one element per "image" passed (we always pass one)
    page_result = raw[0]

    if page_result is None:
        return detections

    # ── New PaddleX-based result format ──────────────────────────────────────
    if hasattr(page_result, "keys") and "rec_texts" in page_result:
        texts  = page_result.get("rec_texts",  [])
        scores = page_result.get("rec_scores", [])
        boxes  = page_result.get("rec_boxes",  [])   # ndarray (N,4) [x1,y1,x2,y2]

        for text, score, box in zip(texts, scores, boxes):
            text = str(text).strip()
            if not text:
                continue
            bbox = [int(box[0]), int(box[1]), int(box[2]), int(box[3])]
            detections.append({
                "text":       text,
                "confidence": round(float(score), 4),
                "bbox":       bbox,
            })

    # ── Legacy list-of-lines format (2.7.x fallback) ─────────────────────────
    elif isinstance(page_result, list):
        for line in page_result:
            if line is None:
                continue
            polygon, (text, confidence) = line
            text = str(text).strip()
            if not text:
                continue
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            bbox = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
            detections.append({
                "text":       text,
                "confidence": round(float(confidence), 4),
                "bbox":       bbox,
            })

    return detections


# ---------------------------------------------------------------------------
# Top-level helper: file → OCR detections
# ---------------------------------------------------------------------------
def extract_ocr_from_file(file_path: str) -> list[dict]:
    """
    Accept a PDF or image file and return all OCR detections combined.

    For PDFs every page is processed; results are concatenated.
    For images a single pass is performed.

    Returns:
        Combined list of {text, confidence, bbox} dicts.
    """
    ext = os.path.splitext(file_path)[-1].lower()

    if ext == ".pdf":
        images = pdf_to_images(file_path)
    else:
        pil_img = Image.open(file_path).convert("RGB")
        images = [np.array(pil_img)]

    all_detections: list[dict] = []
    for img in images:
        all_detections.extend(run_ocr_on_image(img))

    return all_detections
