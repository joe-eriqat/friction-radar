"""Score the relevance gate against a labeled key.

Runs the Layer-1 relevance gate over a labeled comment set and compares its keep/drop
decisions to the ground-truth `about_app` column (yes = on-topic, no = off-topic).

Usage:
    ./venv/bin/python scripts/eval_relevance.py [path/to/key.csv] ["product description"]

CSV columns used: comment_id, about_app (yes|no), comment_text, tricky_for_categorization.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.connector import default_connector  # noqa: E402
from app.processing import RELEVANCE_SYSTEM, _OffTopic, _relevance_user  # noqa: E402
from app.schemas import AnalyzeRequest, FeedbackItem  # noqa: E402

DEFAULT_PRODUCT = (
    "PulseNest Health is a consumer health app for habit-based wellness tracking — sleep, "
    "hydration, movement, medications, and mood — with a NestScore, streaks, caregiver pings, "
    "and wearable integrations."
)


def _col(fields, *candidates):
    lower = {c.lower(): c for c in fields}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    return None


def main(csv_path: Path, product: str) -> int:
    rows = list(csv.DictReader(csv_path.open(newline="")))
    fields = list(rows[0].keys())
    text_col = _col(fields, "comment_text", "comment", "text", "body") or next(
        (c for c in fields if "comment" in c.lower() or "text" in c.lower()), None
    )
    about_col = next((c for c in fields if "about" in c.lower()), None)
    id_col = _col(fields, "comment_id", "id") or fields[0]
    tricky_col = next((c for c in fields if "tricky" in c.lower()), None)
    if not text_col or not about_col:
        print(f"could not find text/about columns in {fields}")
        return 2

    items = [FeedbackItem(text=r[text_col], source="pasted") for r in rows]
    req = AnalyzeRequest(product=product, feedback=items)
    conn = default_connector()
    verdict: _OffTopic = conn.complete_structured(
        system=RELEVANCE_SYSTEM, user=_relevance_user(req), schema=_OffTopic
    )
    dropped = {i for i in verdict.offtopic_indices if 1 <= i <= len(rows)}

    # off-topic = about_app == "no"; everything else (yes / mixed / ambiguous) should be kept.
    tp = fp = fn = tn = 0
    mixed_dropped = mixed_total = 0
    misses: list[tuple[str, str, str, str]] = []
    for i, r in enumerate(rows, 1):
        label = r[about_col].strip().lower()
        truth_off = label == "no"
        pred_off = i in dropped
        if label in ("mixed", "ambiguous"):
            mixed_total += 1
            mixed_dropped += int(pred_off)
        note = (r.get(tricky_col, "").strip() if tricky_col else "") or label
        if truth_off and pred_off:
            tp += 1
        elif truth_off and not pred_off:
            fn += 1
            misses.append((r[id_col], "LEAK — off-topic kept", note, r[text_col]))
        elif not truth_off and pred_off:
            fp += 1
            misses.append((r[id_col], "FALSE DROP — on-topic removed", note, r[text_col]))
        else:
            tn += 1

    n = len(rows)
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    acc = (tp + tn) / n
    print(f"model={conn.model} temp={conn.temperature}  ({csv_path.name})")
    print(f"items={n}  off-topic(no)={tp + fn}  gate dropped={len(dropped)}")
    print(f"off-topic detection: precision={prec:.2f}  recall={rec:.2f}  | overall accuracy={acc:.2f}")
    print(f"confusion: TP={tp}  FN(leak)={fn}  FP(false drop)={fp}  TN={tn}")
    if mixed_total:
        print(f"mixed/ambiguous: {mixed_dropped}/{mixed_total} dropped (these are judgment calls)")
    if misses:
        print("\nmisclassifications:")
        for cid, kind, note, text in misses:
            print(f"  {cid}  [{kind}]  ({note})\n      {text[:100]}")
    else:
        print("\nno misclassifications.")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "pulsenest_health_classifier_key.csv"
    prod = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PRODUCT
    raise SystemExit(main(path, prod))
