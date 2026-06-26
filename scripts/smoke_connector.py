"""Live smoke test for the LLM Connector (spec 02) against a real provider.

Reads OPENAI_API_KEY (and optional FRICTION_RADAR_MODEL / FRICTION_RADAR_LLM_BASE_URL)
from the repo-root .env or the environment, then makes real calls. Run:

    ./venv/bin/python scripts/smoke_connector.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import connector as conn  # noqa: E402
from app.schemas import OnboardingReport  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SYSTEM = (
    "You are an onboarding-intelligence analyst. Given a product and a list of public "
    "feedback items, cluster them into themes (success / failure / churn), score severity, "
    "and give one actionable recommendation per theme. Ground every quote in the input."
)

ITEMS = [
    "Setup was way more painful than I expected; I gave up halfway and came back the next day.",
    "The first summary showed up automatically — didn't have to configure anything to see value.",
    "Pricing is sneaky. Hit the free wall mid-month with zero warning, felt baited.",
    "Switched back to a competitor. Their onboarding just worked.",
]
USER = "Product: AI meeting-notes app\n\nFeedback items:\n" + "\n".join(
    f"{i + 1}. {t}" for i, t in enumerate(ITEMS)
)


def _run(label: str, c: conn.LiteLLMConnector) -> bool:
    print(f"\n=== {label} ===")
    try:
        report = c.complete_structured(system=SYSTEM, user=USER, schema=OnboardingReport)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return False
    assert isinstance(report, OnboardingReport)
    print(f"OK — {len(report.themes)} theme(s). summary: {report.summary[:120]}")
    for t in report.themes[:3]:
        print(f"  - [{t.type.value}/{t.severity.value}] {t.title} (freq {t.frequency})")
    return True


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get(
        "FRICTION_RADAR_LLM_BASE_URL"
    ):
        print("No OPENAI_API_KEY (or FRICTION_RADAR_LLM_BASE_URL) found.")
        print("Add OPENAI_API_KEY=sk-... to the repo-root .env, then re-run.")
        return 2

    model = os.environ.get("FRICTION_RADAR_MODEL", conn.DEFAULT_MODEL)
    base_url = os.environ.get("FRICTION_RADAR_LLM_BASE_URL")
    print(f"model={model}  base_url={base_url or '(default api.openai.com)'}")
    print(f"strict supported for this model: {conn._supports_strict(model)}")

    api_key = os.environ.get("OPENAI_API_KEY")
    ok = True
    # 1) default path (strict auto-detected — strict for gpt-4o-mini)
    ok &= _run("default (auto strict)", conn.default_connector())
    # 2) force JSON-mode + validate path, to prove the fallback works against the provider
    ok &= _run(
        "forced JSON-mode fallback",
        conn.LiteLLMConnector(model=model, api_key=api_key, base_url=base_url, strict=False),
    )

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
