"""Quick end-to-end check: load the sample dataset, run the analyzer, print the report.

    ./venv/bin/python scripts/smoke_test.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analyzer import analyze  # noqa: E402
from app.schemas import AnalyzeRequest  # noqa: E402

sample = json.loads((Path(__file__).resolve().parent.parent / "data" / "sample_feedback.json").read_text())
req = AnalyzeRequest(**sample)
report = analyze(req)

print(f"PRODUCT: {report.product}")
print(f"SUMMARY: {report.summary}\n")
print(f"THEMES ({len(report.themes)}):")
for t in report.themes:
    print(f"  [{t.type.value:7}] [{t.severity.value:6}] {t.title}  ({t.frequency} mentions, stage={t.onboarding_stage})")
    print(f"            → {t.recommendation}")
print("\nOK: valid OnboardingReport returned and validated.")
