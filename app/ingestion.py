"""Ingestion (spec 03): any source -> normalized list[FeedbackItem].

No LLM runs here — ingestion only collects and normalizes; all interpretation happens
downstream in AI Processing. This module ships the DemoAdapter first; Upload/Scrape are
additive later with zero downstream change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .schemas import AnalyzeRequest, FeedbackItem

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE_FILE = _REPO_ROOT / "data" / "sample_feedback.json"


def normalize(items: List[FeedbackItem]) -> List[FeedbackItem]:
    """Strip text, drop blanks, dedupe exact-duplicate text (keep first + its metadata)."""
    out: list[FeedbackItem] = []
    seen: set[str] = set()
    for item in items:
        text = item.text.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item.model_copy(update={"text": text}))
    return out


class DemoAdapter:
    """Load the bundled presaved feedback set."""

    def __init__(self, sample_file: Path | None = None) -> None:
        self._file = sample_file or _SAMPLE_FILE

    def load(self, dataset: str = "default") -> List[FeedbackItem]:
        if dataset != "default":
            raise ValueError(f"Unknown demo dataset: {dataset!r}")
        data = json.loads(self._file.read_text())
        items = [
            FeedbackItem(text=row, source="demo")
            if isinstance(row, str)
            else FeedbackItem(**{"source": "demo", **row})
            for row in data.get("feedback", [])
        ]
        items = normalize(items)
        if not items:
            raise ValueError("no usable feedback found")
        return items


def demo_request(sample_file: Path | None = None) -> AnalyzeRequest:
    """Convenience for the demo path: the sample's product + its normalized items."""
    path = sample_file or _SAMPLE_FILE
    data = json.loads(path.read_text())
    return AnalyzeRequest(product=data["product"], feedback=DemoAdapter(path).load())
