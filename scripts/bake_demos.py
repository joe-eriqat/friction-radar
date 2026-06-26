#!/usr/bin/env python3
"""Bake the demo assets that power LLM-free / static demo mode (spec 08).

For each authored source in docs/*Demo.txt this writes three committed artifacts:

  data/demos/<id>.json          the dataset  {name, product, feedback:[{text, source}]}
  data/demos/canned/<id>.json   a real ReportView captured by running the live pipeline
  data/demos/index.json         manifest the static frontend reads (it can't glob a dir)

Datasets come two ways:
  * "clean"  — structured [ID] platform=… blocks, parsed deterministically (no LLM).
  * "messy"  — deliberately inconsistent dumps, parsed by the live UploadAdapter segmenter.

The canned reports are the ONLY place a token is spent, and only here, by the author. Run
once with a funded key to (re)generate; the committed output then drives the free demo.

    ./venv/bin/python scripts/bake_demos.py            # all demos
    ./venv/bin/python scripts/bake_demos.py staynest   # one (skips others' LLM cost)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from app import ingestion, output, processing  # noqa: E402
from app.schemas import AnalyzeRequest, FeedbackItem  # noqa: E402

DOCS = REPO / "docs"
DEMOS = REPO / "data" / "demos"
CANNED = DEMOS / "canned"

# id -> (display name, source filename, mode). Order = picker order; lead with the messiest
# dumps so the demo opens on the "look what it untangles" case, not a tidy list.
DEMOS_SPEC = {
    "auraquill": ("AuraQuill — AI marketing", "AuraQuill Demo.txt", "messy"),
    "lumenledger": ("LumenLedger — personal finance", "LumenLedger Demo.txt", "messy"),
    "staynest": ("StayNest — vacation rentals", "StayNest Demo.txt", "clean"),
}

# ---- source splitting --------------------------------------------------------------

def _split_source(path: Path) -> tuple[str, str]:
    """Return (product description, raw comment block) from a --SECTION authored file."""
    text = path.read_text(encoding="utf-8")
    desc, _, rest = text.partition("--COMMENT DATA")
    desc = desc.replace("--COMPANY DESCRIPTION", "")
    product = " ".join(line.strip() for line in desc.splitlines() if line.strip()).strip()
    return product, rest.strip()


# ---- clean (deterministic) parser --------------------------------------------------

_HEADER_RE = re.compile(r"^\[(?P<id>[^\]]+)\]\s*(?P<meta>.*)$")
_RULE_RE = re.compile(r"^[=\-]{3,}\s*$")
_DOC_RE = re.compile(r"^DOC-\d+", re.I)


def _platform(meta: str) -> str:
    for part in meta.split("|"):
        part = part.strip()
        if part.startswith("platform="):
            return part[len("platform="):].strip()
    return "demo"


def _parse_clean(block: str) -> list[FeedbackItem]:
    items: list[FeedbackItem] = []
    cur_src: str | None = None
    cur_text: list[str] = []

    def flush() -> None:
        nonlocal cur_text
        if cur_text and cur_src is not None:
            text = " ".join(t.strip() for t in cur_text).strip()
            if text:
                items.append(FeedbackItem(text=text, source=cur_src))
        cur_text = []

    for raw in block.splitlines():
        s = raw.strip()
        if _RULE_RE.match(s) or _DOC_RE.match(s):
            flush()
            continue
        m = _HEADER_RE.match(s)
        if m:
            flush()
            cur_src = _platform(m.group("meta"))
            continue
        if not s:
            flush()
            continue
        if cur_src is not None:
            cur_text.append(s)
    flush()
    return items


# ---- messy (LLM segmenter) parser --------------------------------------------------

def _parse_messy(block: str) -> list[FeedbackItem]:
    """Force the live UploadAdapter segmenter — verbatim, verified against the source.
    fmt="messy" bypasses the auto-detector (these dumps are blank-line separated, which the
    heuristic would mistake for clean paragraphs)."""
    return ingestion.UploadAdapter().load(block, fmt="messy", source="demo")


# ---- baking ------------------------------------------------------------------------

def _dataset(demo_id: str) -> dict:
    name, fname, mode = DEMOS_SPEC[demo_id]
    product, block = _split_source(DOCS / fname)
    items = _parse_clean(block) if mode == "clean" else _parse_messy(block)
    if not items:
        raise ValueError(f"{demo_id}: no feedback parsed from {fname}")
    return {
        "name": name,
        "product": product,
        # the original messy dump — shown verbatim in the demo so visitors see the input the
        # pipeline had to parse (headers, separators, metadata, off-topic noise), not just the
        # clean result. `feedback` is what parsing recovered from it.
        "raw": block,
        "feedback": [it.model_dump(exclude_none=True) for it in items],
    }


def _write_canned(demo_id: str, data: dict) -> None:
    """Run the live pipeline on a dataset and write its canned ReportView (spends tokens)."""
    print(f"[{demo_id}] running live pipeline (this spends tokens)…", flush=True)
    req = AnalyzeRequest(product=data["product"], feedback=data["feedback"])
    report = processing.analyze(req)
    view = output.view_model(report)
    (CANNED / f"{demo_id}.json").write_text(
        json.dumps(view.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[{demo_id}] {view.theme_count} themes, {view.relevant_count}/{view.total_feedback} "
        f"relevant, {len(view.comments)} comments classified → canned/{demo_id}.json",
        flush=True,
    )


def bake_one(demo_id: str) -> None:
    """Full bake: re-parse the source dump into a dataset, then capture a canned report."""
    print(f"[{demo_id}] parsing dataset…", flush=True)
    data = _dataset(demo_id)
    (DEMOS / f"{demo_id}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[{demo_id}] {len(data['feedback'])} items → data/demos/{demo_id}.json", flush=True)
    _write_canned(demo_id, data)


def recan_one(demo_id: str) -> None:
    """Regenerate only the canned report from the committed dataset (no re-segmentation)."""
    data = json.loads((DEMOS / f"{demo_id}.json").read_text())
    print(f"[{demo_id}] re-running pipeline on committed dataset ({len(data['feedback'])} items)…",
          flush=True)
    _write_canned(demo_id, data)


def write_manifest() -> None:
    """index.json lists every demo that has BOTH a dataset and a canned report."""
    entries = []
    for demo_id, (name, _f, _m) in DEMOS_SPEC.items():
        ds, cn = DEMOS / f"{demo_id}.json", CANNED / f"{demo_id}.json"
        if ds.exists() and cn.exists():
            data = json.loads(ds.read_text())
            entries.append({
                "id": demo_id,
                "name": str(data.get("name") or name),
                "product": data.get("product", ""),
                "count": len(data.get("feedback", [])),
            })
    (DEMOS / "index.json").write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"manifest: {len(entries)} demo(s) → data/demos/index.json")


def main() -> None:
    DEMOS.mkdir(parents=True, exist_ok=True)
    CANNED.mkdir(parents=True, exist_ok=True)
    args = sys.argv[1:]
    # --from-datasets: skip re-parsing the source dumps (and the segmenter) — just regenerate
    # the canned reports from the committed datasets. Use after a pipeline/schema change.
    from_datasets = "--from-datasets" in args
    wanted = [a for a in args if not a.startswith("--")] or list(DEMOS_SPEC)
    unknown = [d for d in wanted if d not in DEMOS_SPEC]
    if unknown:
        sys.exit(f"unknown demo id(s): {', '.join(unknown)}. known: {', '.join(DEMOS_SPEC)}")
    for demo_id in wanted:
        (recan_one if from_datasets else bake_one)(demo_id)
    write_manifest()


if __name__ == "__main__":
    main()
