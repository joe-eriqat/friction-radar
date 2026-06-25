"""The AI core: turn raw public feedback into a structured onboarding report.

A single Claude call does sentiment classification, theme clustering, severity scoring,
and recommendation generation. We use `client.messages.parse(output_format=...)` so the
response is validated against `OnboardingReport` before it ever reaches the caller — no
hand-rolled JSON schema, no brittle string parsing.
"""

from __future__ import annotations

import os

import anthropic

from .schemas import AnalyzeRequest, OnboardingReport

# Per the Anthropic model guidance, default to the most capable Opus tier. Override via
# FRICTION_RADAR_MODEL (e.g. claude-haiku-4-5) for cheaper/faster demo runs.
DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """\
You are Friction Radar, an onboarding-intelligence analyst. You read public customer
feedback (reviews, Reddit/forum comments, app-store posts) about a product and surface
where users succeed or fail during onboarding and early activation.

Given a product and a set of feedback items, do the following:
- Classify each item by sentiment and the onboarding stage it speaks to.
- Cluster related items into themes. Each theme is either a success point (clarity,
  delight, fast activation, a "magic moment"), a failure point (confusion, friction,
  unmet expectations), or a churn/drop-off signal (language that the user gave up or
  switched away).
- Score each theme's severity by its impact on activation, and set `frequency` to how
  many supplied comments express it.
- Back every theme with representative quotes drawn from the actual input — never invent
  quotes or feedback that was not provided.
- Give each theme a concrete, actionable onboarding recommendation.

Order themes most-to-least important (severity first, then frequency). Ground the report
strictly in the supplied feedback; if the data is thin, say so in the summary rather than
speculating.
"""


def get_client() -> anthropic.Anthropic:
    """Construct the SDK client. Reads ANTHROPIC_API_KEY from the environment."""
    return anthropic.Anthropic()


def _model() -> str:
    return os.environ.get("FRICTION_RADAR_MODEL", DEFAULT_MODEL)


def _build_user_content(req: AnalyzeRequest) -> str:
    items = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(req.feedback))
    return (
        f"Product / category: {req.product}\n\n"
        f"Public feedback items ({len(req.feedback)}):\n{items}\n\n"
        "Produce the onboarding-intelligence report."
    )


def analyze(req: AnalyzeRequest, client: anthropic.Anthropic | None = None) -> OnboardingReport:
    """Run the analysis and return a validated OnboardingReport."""
    if not req.feedback:
        raise ValueError("No feedback items supplied to analyze.")

    client = client or get_client()
    response = client.messages.parse(
        model=_model(),
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_content(req)}],
        output_format=OnboardingReport,
    )

    report = response.parsed_output
    if report is None:
        # parsed_output is None if the model refused or output didn't validate.
        raise RuntimeError(
            f"Analysis did not return a valid report (stop_reason={response.stop_reason})."
        )
    # The model may echo back its own product phrasing; keep the caller's label.
    report.product = req.product
    return report
