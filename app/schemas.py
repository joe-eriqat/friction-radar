"""Pydantic models shared across the app.

`OnboardingReport` is the public, stored output contract. AI Processing builds it by having
the model assign feedback items to themes by index (see `app/processing.py`); a deterministic
step then counts members and attaches a sample of their quotes with provenance — the model
never regenerates item text.
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
    """One clustered onboarding theme.

    `frequency` is the real count of feedback items assigned to this theme; `evidence` is a
    representative *sample* of those items' quotes (not necessarily all `frequency` of them).
    """

    title: str
    type: ThemeType
    severity: Severity
    onboarding_stage: str
    frequency: int
    evidence: List[Evidence]
    recommendation: str


class CommentClassification(BaseModel):
    """One input comment with what the pipeline decided about it — the full audit trail.

    Lets a report account for *every* submitted comment (not just the sampled quotes): whether
    the relevance gate kept it, and which theme the classifier assigned it to.
    """

    text: str
    source: Optional[str] = None
    relevant: bool                     # False = dropped by the relevance gate (off-topic)
    theme: Optional[str] = None        # assigned theme title; None if off-topic or unassigned


class OnboardingReport(BaseModel):
    """The full prioritized onboarding-intelligence report for one product."""

    product: str
    summary: str
    themes: List[Theme]
    total_feedback: int = 0   # items submitted
    relevant_count: int = 0   # items kept after the relevance gate (themes draw from these)
    comments: List[CommentClassification] = []  # every input comment + its relevance/theme


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
