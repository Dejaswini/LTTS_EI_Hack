# CAD Drawing Intelligence Assistant

> **Hackathon Milestone 1** — Upload · Classify · Extract · JSON

Automatically classifies uploaded engineering drawings as **Part** or **Assembly**, runs OCR via PaddleOCR, and outputs fully-structured JSON.

---

## Quick Start

```bash
# 1. Create virtual environment
python -m venv cad
cad\Scripts\activate          # Windows
# source cad/bin/activate     # Linux / macOS

# 2. Upgrade pip
python -m pip install --upgrade pip

# 3. Install dependencies (order matters for PaddlePaddle)
pip install paddlepaddle==2.6.2
pip install paddleocr==2.8.1
pip install fastapi==0.115.0 uvicorn==0.30.6
pip install pymupdf==1.24.10
pip install opencv-python==4.10.0.84
pip install numpy==1.26.4 Pillow==10.4.0
pip install python-multipart==0.0.9
pip install aiofiles==24.1.0
pip install python-dotenv==1.0.1
pip install streamlit==1.38.0 requests==2.32.3

# 4. Start the backend (Terminal 1)
cd backend
uvicorn app:app --reload

# 5. Start the frontend (Terminal 2)
cd frontend
streamlit run streamlit_app.py
```

---

## Project Structure

```
cadproj/
├── backend/
│   ├── app.py                   # FastAPI entry point
│   ├── routes/
│   │   └── upload.py            # POST /upload · GET /result/{fn}
│   ├── services/
│   │   ├── ocr_service.py       # PDF→image (PyMuPDF) + PaddleOCR
│   │   ├── classifier.py        # Keyword-based Part / Assembly classifier
│   │   ├── part_parser.py       # Title block + dimensions + tolerances
│   │   ├── assembly_parser.py   # BOM table extraction
│   │   └── json_generator.py    # Structured JSON builder + file persistence
│   ├── uploads/                 # Temporary uploaded files
│   └── output/                  # Generated JSON results
├── frontend/
│   └── streamlit_app.py         # Dark-theme Streamlit UI
├── requirements.txt
└── README.md
```

---

## API Reference

### `POST /upload`

Upload an engineering drawing (PDF or image).

**Request** — `multipart/form-data`

| Field | Type   | Description             |
|-------|--------|-------------------------|
| file  | binary | PDF / PNG / JPG / TIFF  |

**Response** — JSON

```json
{
  "drawing_type": "part",
  "output_file": "shaft_part_output.json",
  "meta": {
    "source_file": "shaft.png",
    "drawing_type": "part",
    "processed_at": "2025-01-01T12:00:00Z",
    "total_ocr_hits": 47
  },
  "extracted_data": { ... }
}
```

---

### `GET /result/{filename}`

Retrieve a previously saved result.

```
GET http://localhost:8000/result/shaft_part_output.json
```

---

### `GET /results`

List all saved result filenames.

```json
{ "files": ["shaft_part_output.json", "vise_assembly_output.json"] }
```



## Environment Requirements

| Package           | Version   |
|-------------------|-----------|
| Python            | 3.11.x    |
| fastapi           | 0.115.0   |
| uvicorn           | 0.30.6    |
| paddleocr         | 2.8.1     |
| paddlepaddle      | 2.6.2     |
| PyMuPDF           | 1.24.10   |
| opencv-python     | 4.10.0.84 |
| numpy             | 1.26.4    |
| Pillow            | 10.4.0    |
| python-multipart  | 0.0.9     |
| pydantic          | 2.9.2     |
| aiofiles          | 24.1.0    |
| python-dotenv     | 1.0.1     |
| streamlit         | 1.38.0    |

> ⚠️ Do **not** use Python 3.13 — PaddlePaddle requires Python 3.11.

---

## Architecture

```
Upload (PDF / Image)
        │
        ▼
 ocr_service.py
  ├─ pdf_to_images()   (PyMuPDF)
  └─ run_ocr_on_image() (PaddleOCR)
        │
        ▼ detections [ {text, confidence, bbox} ]
        │
   classifier.py  ──► "part" | "assembly"
        │
        ├── part_parser.py     → title block fields + dimensions + tolerances
        └── assembly_parser.py → BOM rows (item / part_number / quantity)
        │
        ▼
 json_generator.py  ──► output/{name}_{type}_output.json
        │
        ▼
  FastAPI response  ──► Streamlit UI
```

---


