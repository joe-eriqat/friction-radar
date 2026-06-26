"""Ingestion (spec 03): any source -> normalized list[FeedbackItem].

Mostly deterministic — DemoAdapter, CSV, JSON, and clean free-text never call an LLM. The one
exception is the UploadAdapter's messy free-text fallback: a focused segmentation call whose
output is verified to be verbatim from the source. All interpretation (classify / cluster /
judge) still happens downstream in AI Processing.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from statistics import mean, mode
from typing import List

from pydantic import BaseModel, Field

from .connector import LLMConnector, default_connector
from .schemas import AnalyzeRequest, FeedbackItem

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE_FILE = _REPO_ROOT / "data" / "sample_feedback.json"
_DEMOS_DIR = _REPO_ROOT / "data" / "demos"


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


# ===== DemoAdapter =====================================================================


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


def _demo_files() -> dict[str, Path]:
    """Map demo id -> file. The bundled sample is 'default'; each data/demos/*.json adds one
    (id = filename stem). Drop a new {name?, product, feedback:[...]} json in data/demos/ to
    register another demo — no code change needed."""
    files: dict[str, Path] = {}
    if _SAMPLE_FILE.exists():
        files["default"] = _SAMPLE_FILE
    if _DEMOS_DIR.is_dir():
        for p in sorted(_DEMOS_DIR.glob("*.json")):
            if p.stem != "default":
                files[p.stem] = p
    return files


def available_demos() -> List[dict]:
    """List the registered demo datasets for the picker (id, display name, product, count)."""
    out: list[dict] = []
    for did, path in _demo_files().items():
        try:
            data = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        product = str(data.get("product", "")).strip()
        name = str(data.get("name") or product or did).strip()
        out.append({
            "id": did,
            "name": name,
            "product": product,
            "count": len(data.get("feedback", [])),
        })
    return out


def demo_request(name: str | None = None, sample_file: Path | None = None) -> AnalyzeRequest:
    """Convenience for the demo path: a dataset's product + its normalized items.

    `name` selects a registered demo (default = the bundled sample); `sample_file` overrides
    the path directly (used by tests)."""
    if sample_file is not None:
        path = sample_file
    else:
        path = _demo_files().get(name or "default")
        if path is None:
            raise ValueError(f"Unknown demo dataset: {name!r}")
    data = json.loads(path.read_text())
    return AnalyzeRequest(product=data["product"], feedback=DemoAdapter(path).load())


# ===== UploadAdapter ===================================================================

_TEXT_COLUMN_NAMES = (
    "comment_text", "comment", "text", "review", "feedback", "body", "message", "content",
)
_SEPARATOR_RE = re.compile(r"^\s*[-=*_#~]{3,}\s*$")          # ====, ----, ***, ___
_METADATA_RE = re.compile(r"^\s*[\w/@.\- ]{1,24}:\s*\S")     # short "key: value" line
_TERMINATORS = (".", "!", "?", "…", '"', "'", ")", "]", ":")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


# ---- format detection ----


def _is_csv(raw: str) -> bool:
    if not re.search(r"[,\t;|]", raw):
        return False
    try:
        dialect = csv.Sniffer().sniff(raw[:4000])
    except csv.Error:
        return False
    rows = [r for r in csv.reader(io.StringIO(raw), dialect) if r]
    if len(rows) < 2:
        return False
    counts = [len(r) for r in rows]
    common = mode(counts)
    # tabular = a stable column count >= 2 across most rows
    return common >= 2 and sum(c == common for c in counts) / len(counts) >= 0.8


def _detect_format(raw: str) -> str:
    s = raw.strip()
    if not s:
        return "empty"
    if s[0] in "[{":
        try:
            json.loads(s)
            return "json"
        except ValueError:
            pass
    if _is_csv(raw):
        return "csv"
    return "text"


# ---- structured paths (deterministic) ----


def _pick_text_column(header: list[str], rows: list[list[str]]) -> int:
    lower = [h.strip().lower() for h in header]
    for name in _TEXT_COLUMN_NAMES:
        if name in lower:
            return lower.index(name)
    avgs = [
        mean([len(r[i]) for r in rows if i < len(r)] or [0]) for i in range(len(header))
    ]
    return avgs.index(max(avgs))


def _from_csv(raw: str, source: str) -> list[FeedbackItem]:
    rows = [r for r in csv.reader(io.StringIO(raw)) if r]
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    lower = [h.strip().lower() for h in header]
    text_i = _pick_text_column(header, body or rows)

    def col(*names: str) -> int | None:
        for n in names:
            if n in lower:
                return lower.index(n)
        return None

    src_i = col("source", "platform")
    url_i = col("url", "link")
    date_i = col("date", "created_at")

    def cell(row: list[str], i: int | None) -> str | None:
        return row[i] if i is not None and i < len(row) and row[i].strip() else None

    items = []
    for r in body:
        if text_i >= len(r) or not r[text_i].strip():
            continue
        items.append(
            FeedbackItem(
                text=r[text_i],
                source=cell(r, src_i) or source,
                url=cell(r, url_i),
                date=cell(r, date_i),
            )
        )
    return items


def _from_json(raw: str, source: str) -> list[FeedbackItem]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("JSON feedback must be a list")
    items = []
    for el in data:
        if isinstance(el, str):
            items.append(FeedbackItem(text=el, source=source))
        elif isinstance(el, dict):
            text = next((el[k] for k in _TEXT_COLUMN_NAMES if el.get(k)), None)
            if text:
                items.append(
                    FeedbackItem(
                        text=str(text),
                        source=el.get("source") or source,
                        url=el.get("url"),
                        date=el.get("date"),
                    )
                )
    return items


# ---- free-text: clean vs messy ----


def _looks_messy(text: str) -> bool:
    """Decide whether free-text needs LLM segmentation. Biased toward 'messy' (safe: a false
    positive just costs one correct extra call; a false negative shreds comments)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    if any(_SEPARATOR_RE.match(ln) for ln in lines):
        return True
    metaish = sum(
        1 for ln in lines if not any(c.isalnum() for c in ln) or _METADATA_RE.match(ln.strip())
    )
    if metaish / len(lines) > 0.30:
        return True
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) >= 2:
        return False  # blank-line paragraphs are a reliable delimiter -> clean
    if len(lines) >= 3:
        unterminated = sum(1 for ln in lines if not ln.rstrip().endswith(_TERMINATORS))
        if unterminated / len(lines) > 0.5:  # mostly un-terminated -> likely wrapped lines
            return True
    return False


def _split_clean(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) >= 2:
        return paras
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


SEGMENT_SYSTEM = (
    "You are given a block of text that contains several pieces of user feedback (reviews, "
    "comments, posts), possibly mixed with a heading or preamble, separator lines, and metadata "
    "(author, date, platform). Extract each distinct piece of feedback as its own item, copied "
    "VERBATIM from the text. Keep a multi-line comment together as one item. Do NOT include "
    "headings, instructions, separator lines, or metadata, and do NOT paraphrase, summarize, "
    "merge, reorder, or invent — copy the exact original wording."
)


class _Segments(BaseModel):
    comments: List[str] = Field(
        description="Each distinct feedback comment, copied verbatim from the source text."
    )


def _segment(text: str, connector: LLMConnector) -> list[str]:
    # Output scales with the dump size (one item per comment), so give it generous room.
    # (Very large dumps still need chunking — a future enhancement; see spec 03.)
    seg: _Segments = connector.complete_structured(  # type: ignore[assignment]
        system=SEGMENT_SYSTEM, user=text, schema=_Segments, max_tokens=16000
    )
    return seg.comments


def _verify_verbatim(comments: list[str], source: str) -> list[str]:
    """Keep only comments that appear (normalized) in the source — drops paraphrase/invention.

    Substring (not equality) so the same check later supports pulling a sub-span of a comment.
    """
    src = _norm(source)
    return [c for c in comments if _norm(c) and _norm(c) in src]


class UploadAdapter:
    """Parse a CSV / JSON / free-text dump into clean FeedbackItems.

    Deterministic for CSV / JSON and clean free-text; messy free-text falls back to an LLM
    segmentation call whose output is verified verbatim against the source.
    """

    def __init__(self, connector: LLMConnector | None = None) -> None:
        self._connector = connector

    def load(self, raw: str, *, fmt: str = "auto", source: str = "upload") -> list[FeedbackItem]:
        detected = _detect_format(raw) if fmt == "auto" else fmt
        if detected == "empty":
            raise ValueError("empty input")
        if detected == "json":
            items = _from_json(raw, source)
        elif detected == "csv":
            items = _from_csv(raw, source)
        elif _looks_messy(raw):
            conn = self._connector or default_connector()
            comments = _verify_verbatim(_segment(raw, conn), raw)
            items = [FeedbackItem(text=c, source=source) for c in comments]
        else:
            items = [FeedbackItem(text=t, source=source) for t in _split_clean(raw)]
        items = normalize(items)
        if not items:
            raise ValueError("no usable feedback found")
        return items
