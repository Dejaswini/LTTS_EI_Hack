# backend/services/batch_processor.py
# Splits multi-page PDFs and ZIPs into individual drawing images.

from __future__ import annotations
import os, zipfile, shutil, uuid
import fitz
import numpy as np
from PIL import Image

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
DPI = 300   # 300 DPI for production quality


def process_upload(file_path: str, doc_id: str) -> list[dict]:
    """
    Split uploaded file into individual drawing image records.

    Returns list of:
        {page_num, display_name, image_path}
    """
    ext = os.path.splitext(file_path)[-1].lower()
    out_dir = os.path.join(UPLOAD_DIR, doc_id, "pages")
    os.makedirs(out_dir, exist_ok=True)

    if ext == ".zip":
        return _process_zip(file_path, doc_id, out_dir)
    elif ext == ".pdf":
        return _process_pdf(file_path, doc_id, out_dir)
    else:
        # Single image
        return _process_image(file_path, doc_id, out_dir)


def _process_pdf(pdf_path: str, doc_id: str, out_dir: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages = []
    zoom = DPI / 72
    mat = fitz.Matrix(zoom, zoom)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_path = os.path.join(out_dir, f"page_{i+1:03d}.png")
        img.save(img_path, "PNG")
        pages.append({
            "page_num":     i + 1,
            "display_name": f"Image {i+1}",
            "image_path":   img_path,
        })
    doc.close()
    return pages


def _process_zip(zip_path: str, doc_id: str, out_dir: str) -> list[dict]:
    pages = []
    count = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = sorted(n for n in zf.namelist()
                       if not n.startswith("__") and
                       os.path.splitext(n)[-1].lower()
                       in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".pdf"))
        for name in names:
            data = zf.read(name)
            ext = os.path.splitext(name)[-1].lower()
            tmp = os.path.join(out_dir, f"zip_{count}{ext}")
            with open(tmp, "wb") as f:
                f.write(data)
            if ext == ".pdf":
                sub = _process_pdf(tmp, doc_id, out_dir)
                # Re-number
                for s in sub:
                    count += 1
                    s["display_name"] = f"Image {count}"
                    s["page_num"] = count
                pages.extend(sub)
            else:
                count += 1
                img_path = os.path.join(out_dir, f"page_{count:03d}.png")
                Image.open(tmp).convert("RGB").save(img_path, "PNG")
                pages.append({
                    "page_num": count,
                    "display_name": f"Image {count}",
                    "image_path": img_path,
                })
    return pages


def _process_image(img_path: str, doc_id: str, out_dir: str) -> list[dict]:
    img_out = os.path.join(out_dir, "page_001.png")
    Image.open(img_path).convert("RGB").save(img_out, "PNG")
    return [{"page_num": 1, "display_name": "Image 1", "image_path": img_out}]
