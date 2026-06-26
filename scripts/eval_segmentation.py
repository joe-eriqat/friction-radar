"""Segmentation eval: can the UploadAdapter recover real comments from a messy dump?

Builds a deliberately messy text dump from a labelled CSV — preamble, `====` separator bars,
hard-wrapped multi-line comments, and per-comment metadata lines — then runs UploadAdapter and
reports how many of the original comments are recovered verbatim (and any spurious extras).

Usage: ./venv/bin/python scripts/eval_segmentation.py [path/to/key.csv]
"""

from __future__ import annotations

import csv
import sys
import textwrap
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.ingestion import UploadAdapter, _looks_messy, _norm  # noqa: E402


def _text_col(fields: list[str]) -> str:
    lower = {c.lower(): c for c in fields}
    for c in ("comment_text", "comment", "text", "review", "feedback", "body"):
        if c in lower:
            return lower[c]
    for c in fields:  # substring fallback (e.g. exact_comment_text)
        if "comment" in c.lower() or "text" in c.lower():
            return c
    return fields[0]


def build_messy_dump(comments: list[str]) -> str:
    lines = [
        "StayNest feedback export — Q2 2026",
        "Pulled from Reddit, app stores, and G2. Internal review only — do not share.",
        "=" * 48,
        "",
    ]
    for i, c in enumerate(comments):
        if i and i % 5 == 0:
            lines += ["=" * 48, ""]
        # hard-wrap longer comments to simulate multi-line wrapping
        lines.append("\n".join(textwrap.wrap(c, 64)) if len(c) > 80 else c)
        lines.append(f"  — u/user{i:02d} · 2026-0{i % 6 + 1}-1{i % 9} · reddit")
        lines.append("")
    return "\n".join(lines)


def main(path: Path) -> int:
    rows = list(csv.DictReader(path.open(newline="")))
    tc = _text_col(list(rows[0].keys()))
    originals = [r[tc] for r in rows if r[tc].strip()]
    dump = build_messy_dump(originals)
    print(f"originals={len(originals)}  dump={len(dump.splitlines())} lines / {len(dump)} chars")
    print(f"_looks_messy -> {_looks_messy(dump)} (should be True)")

    items = UploadAdapter().load(dump)  # real LLM via default connector
    out = [_norm(it.text) for it in items]
    onorm = [_norm(o) for o in originals]

    recovered = sum(1 for o in onorm if any(o in t or t in o for t in out))
    spurious = sum(1 for t in out if not any(o in t or t in o for o in onorm))
    print(f"\nitems returned = {len(items)}")
    print(f"recovered originals = {recovered}/{len(originals)}  (recall {recovered / len(originals):.2f})")
    print(f"spurious items (match no original) = {spurious}")

    misses = [originals[i] for i, o in enumerate(onorm) if not any(o in t or t in o for t in out)]
    if misses:
        print("\nsample misses:")
        for m in misses[:6]:
            print(f"  - {m[:90]}")
    return 0


if __name__ == "__main__":
    p = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "docs" / "staynest_vacation_rental_classifier_key.csv"
    )
    raise SystemExit(main(p))
