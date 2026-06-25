"""Pydantic models shared by the API, the analyzer, and the structured-output contract.

The `OnboardingReport` model is passed directly to `client.messages.parse(...)` as the
output format, so its shape *is* the JSON schema Claude is constrained to. Keep the
fields simple (str / enum / int / list) — structured outputs do not support numeric or
string-length constraints.
"""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class ThemeType(str, Enum):
    """Which side of the onboarding experience a theme describes."""

    success = "success"  # clarity, delight, fast activation, a "magic moment"
    failure = "failure"  # confusion, friction, unmet expectations
    churn = "churn"      # language signalling the user abandoned / switched away


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Theme(BaseModel):
    """One clustered onboarding theme, backed by representative user quotes."""

    title: str = Field(description="Short, specific name for the theme.")
    type: ThemeType
    severity: Severity = Field(
        description="Impact on activation: high = blocks/strongly drives activation."
    )
    onboarding_stage: str = Field(
        description="Where in onboarding this surfaces, e.g. signup, setup, "
        "first-use, integrations, pricing-discovery, activation."
    )
    frequency: int = Field(
        description="How many of the supplied comments express this theme."
    )
    evidence: List[str] = Field(
        description="Verbatim or lightly-trimmed representative quotes from the input."
    )
    recommendation: str = Field(
        description="Concrete, actionable onboarding change addressing this theme."
    )


class OnboardingReport(BaseModel):
    """The full prioritized onboarding-intelligence report for one product."""

    product: str = Field(description="The product / category the report is about.")
    summary: str = Field(
        description="2-4 sentence executive summary of activation strengths and risks."
    )
    themes: List[Theme] = Field(
        description="Clustered themes, ordered most to least important "
        "(severity, then frequency)."
    )


# ---- API request / response wrappers -------------------------------------------------


class AnalyzeRequest(BaseModel):
    product: str = Field(description="Product, competitor, or category name.")
    feedback: List[str] = Field(
        default_factory=list,
        description="Individual pieces of public feedback (reviews, comments, posts).",
    )


class StoredReport(BaseModel):
    id: int
    created_at: str
    product: str
    report: OnboardingReport
