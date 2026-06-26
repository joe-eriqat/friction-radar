"""FastAPI app: serves the single-page UI and the analysis API.

Run with:  uvicorn app.main:app --reload   (or ./run.sh)
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ingestion, output, store
from .processing import analyze
from .schemas import AnalyzeRequest, OnboardingReport, StoredReport

load_dotenv()  # pick up .env if present (OPENAI_API_KEY, FRICTION_RADAR_MODEL, ...)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STATIC_DIR = _REPO_ROOT / "static"

app = FastAPI(title="Friction Radar", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    store.init_db()


@app.get("/api/sample")
def get_sample() -> AnalyzeRequest:
    """Load the bundled demo dataset (no live scraping required)."""
    return ingestion.demo_request()


class IngestRequest(BaseModel):
    product: str = ""
    raw: str = ""
    source: str = "pasted"


@app.post("/api/ingest", response_model=AnalyzeRequest)
def post_ingest(req: IngestRequest) -> AnalyzeRequest:
    """Parse a raw paste / file dump (CSV / JSON / messy text) into clean feedback items."""
    if not req.raw.strip():
        raise HTTPException(status_code=400, detail="No input to parse.")
    try:
        items = ingestion.UploadAdapter().load(req.raw, source=req.source or "pasted")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # segmentation / connector failure
        raise HTTPException(status_code=502, detail=f"Could not parse input: {exc}") from exc
    return AnalyzeRequest(product=req.product, feedback=items)


@app.post("/api/analyze", response_model=StoredReport)
def post_analyze(req: AnalyzeRequest) -> StoredReport:
    """Run feedback through analysis, persist, and return the stored report."""
    if not req.product.strip():
        raise HTTPException(status_code=400, detail="A product/category name is required.")
    if not req.feedback:
        raise HTTPException(status_code=400, detail="At least one feedback item is required.")
    try:
        report: OnboardingReport = analyze(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # connector / provider failure
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


@app.get("/api/reports/{report_id}/view", response_model=output.ReportView)
def get_report_view(report_id: int) -> output.ReportView:
    """Prioritized, presentation-ready view of a stored report (for the SPA)."""
    stored = store.get_report(report_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return output.view_model(stored.report)


@app.get("/api/reports/{report_id}/export")
def export_report(report_id: int, format: str = "md") -> PlainTextResponse:
    """Export a stored report as share-ready Markdown or canonical JSON."""
    stored = store.get_report(report_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    if format == "md":
        return PlainTextResponse(output.to_markdown(stored.report), media_type="text/markdown")
    if format == "json":
        return PlainTextResponse(output.to_json(stored.report), media_type="application/json")
    raise HTTPException(status_code=400, detail="format must be 'md' or 'json'.")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


# Serve remaining static assets (CSS/JS) if we add any later.
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
