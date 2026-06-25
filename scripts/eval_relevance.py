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


def main(csv_path: Path, product: str) -> int:
    rows = list(csv.DictReader(csv_path.open(newline="")))
    items = [FeedbackItem(text=r["comment_text"], source="pasted") for r in rows]
    req = AnalyzeRequest(product=product, feedback=items)

    conn = default_connector()
    verdict: _OffTopic = conn.complete_structured(
        system=RELEVANCE_SYSTEM, user=_relevance_user(req), schema=_OffTopic
    )
    dropped = {i for i in verdict.offtopic_indices if 1 <= i <= len(rows)}

    tp = fp = fn = tn = 0
    misses: list[tuple[str, str, str, str]] = []
    for i, r in enumerate(rows, 1):
        truth_off = r["about_app"].strip().lower() == "no"
        pred_off = i in dropped
        tricky = r.get("tricky_for_categorization", "").strip()
        if truth_off and pred_off:
            tp += 1
        elif truth_off and not pred_off:
            fn += 1
            misses.append((r["comment_id"], "LEAK — off-topic kept", tricky, r["comment_text"]))
        elif not truth_off and pred_off:
            fp += 1
            misses.append((r["comment_id"], "FALSE DROP — real feedback removed", tricky, r["comment_text"]))
        else:
            tn += 1

    n = len(rows)
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    acc = (tp + tn) / n
    print(f"model={conn.model} temp={conn.temperature}")
    print(f"items={n}  ground-truth off-topic={tp + fn}  gate dropped={len(dropped)}")
    print(f"off-topic detection: precision={prec:.2f}  recall={rec:.2f}  | overall accuracy={acc:.2f}")
    print(f"confusion: TP(correct drop)={tp}  FN(leak)={fn}  FP(false drop)={fp}  TN(correct keep)={tn}")
    print(f"tricky cases: {sum(1 for r in rows if r.get('tricky_for_categorization','').strip().lower()=='yes')}")
    if misses:
        print("\nmisclassifications:")
        for cid, kind, tricky, text in misses:
            print(f"  {cid}  [{kind}]  tricky={tricky or 'no'}\n      {text[:100]}")
    else:
        print("\nno misclassifications — perfect relevance separation.")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "pulsenest_health_classifier_key.csv"
    prod = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PRODUCT
    raise SystemExit(main(path, prod))
