"""Pydantic models shared across the app.

`OnboardingReport` is the public, stored output contract. AI Processing builds it from an
internal model-facing schema (see `app/processing.py`) and attaches evidence provenance
during grounding — the LLM itself only ever produces quote strings, never source/url.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ThemeType(str, Enum):
    """Which side of the onboarding experience a theme describes."""

    success = "success"  # clarity, delight, fast activation, a "magic moment"
    failure = "failure"  # confusion, friction, unmet expectations
    churn = "churn"      # language signalling the user abandoned / switched away


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class FeedbackItem(BaseModel):
    """One piece of public feedback.

    Only `text` is required, so demo/upload stay trivial; metadata is preserved when a
    source (e.g. scraping) provides it.
    """

    text: str
    source: Optional[str] = None   # "demo" | "upload" | "reddit" | "app_store" | ...
    url: Optional[str] = None
    date: Optional[str] = None     # ISO-8601 if known


class Evidence(BaseModel):
    """A representative quote, traced back to the input item it came from."""

    quote: str
    source: Optional[str] = None
    url: Optional[str] = None


class Theme(BaseModel):
    """One clustered onboarding theme, backed by grounded evidence."""

    title: str
    type: ThemeType
    severity: Severity
    onboarding_stage: str
    frequency: int
    evidence: List[Evidence]
    recommendation: str


class OnboardingReport(BaseModel):
    """The full prioritized onboarding-intelligence report for one product."""

    product: str
    summary: str
    themes: List[Theme]


# ---- API request / response wrappers -------------------------------------------------


class AnalyzeRequest(BaseModel):
    product: str = Field(description="Product, competitor, or category name.")
    feedback: List[FeedbackItem] = Field(default_factory=list)

    @field_validator("feedback", mode="before")
    @classmethod
    def _coerce_strings(cls, v: object) -> object:
        """Accept a bare list[str] and promote each string to a FeedbackItem.

        Keeps paste callers (and the current SPA) trivial. Bare strings are tagged
        `source="pasted"` so the evidence still carries a provenance label (adapters that
        supply their own FeedbackItem objects keep their own source: demo/upload/scrape).
        """
        if isinstance(v, list):
            return [{"text": x, "source": "pasted"} if isinstance(x, str) else x for x in v]
        return v


class StoredReport(BaseModel):
    id: int
    created_at: str
    product: str
    report: OnboardingReport
