# backend/app.py  — CAD Drawing Copilot v3.0
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from routes.upload    import router as upload_router     # Phase 1 legacy
from routes.ai        import router as ai_router         # Phase 2 AI
from routes.checklist import router as checklist_router  # Phase 3
from routes.drawing   import router as drawing_router    # Phase 3
from routes.search    import router as search_router     # Phase 3

app = FastAPI(
    title="CAD Drawing Copilot",
    description="Production-ready CAD AI Copilot — OCR + AI extraction + checklist validation",
    version="3.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for d in ["uploads", "output", "outputs"]:
    os.makedirs(d, exist_ok=True)

app.include_router(upload_router)
app.include_router(ai_router)
app.include_router(checklist_router)
app.include_router(drawing_router)
app.include_router(search_router)

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "version": "3.0.0",
            "message": "CAD Drawing Copilot API is running."}
