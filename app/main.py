"""FastAPI app: serves the single-page UI and the analysis API.

Run with:  uvicorn app.main:app --reload   (or ./run.sh)
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import store
from .analyzer import analyze
from .schemas import AnalyzeRequest, OnboardingReport, StoredReport

load_dotenv()  # pick up .env if present; the global env still wins for ANTHROPIC_API_KEY

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STATIC_DIR = _REPO_ROOT / "static"
_SAMPLE_FILE = _REPO_ROOT / "data" / "sample_feedback.json"

app = FastAPI(title="Friction Radar", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    store.init_db()


@app.get("/api/sample")
def get_sample() -> AnalyzeRequest:
    """Load the bundled demo dataset (no live scraping required)."""
    data = json.loads(_SAMPLE_FILE.read_text())
    return AnalyzeRequest(**data)


@app.post("/api/analyze", response_model=StoredReport)
def post_analyze(req: AnalyzeRequest) -> StoredReport:
    """Analyze feedback with Claude, persist, and return the stored report."""
    if not req.product.strip():
        raise HTTPException(status_code=400, detail="A product/category name is required.")
    if not req.feedback:
        raise HTTPException(status_code=400, detail="At least one feedback item is required.")
    try:
        report: OnboardingReport = analyze(req)
    except Exception as exc:  # surface a clean error to the UI
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}") from exc
    return store.save_report(report)


@app.get("/api/reports", response_model=list[StoredReport])
def get_reports() -> list[StoredReport]:
    return store.list_reports()


@app.get("/api/reports/{report_id}", response_model=StoredReport)
def get_one_report(report_id: int) -> StoredReport:
    stored = store.get_report(report_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return stored


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


# Serve remaining static assets (CSS/JS) if we add any later.
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
