"""AI Processing (spec 01): (product, feedback[]) -> grounded OnboardingReport.

Owns the prompt and the output contract. The model is asked for an internal report whose
evidence is just quote strings (it cannot know a quote's provenance); this module then
*grounds* each quote against the actual input items — dropping invented quotes, dropping
themes left with none, attaching the matched item's source/url, and clamping frequency —
before assembling the public `OnboardingReport`. Provider/SDK details live in the Connector.
"""

from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, Field

from .connector import LLMConnector, default_connector
from .schemas import AnalyzeRequest, Evidence, OnboardingReport, Severity, Theme, ThemeType

SYSTEM = (
    "You are an onboarding-intelligence analyst. Given a product and a list of public "
    "customer feedback items, cluster them into themes (success / failure / churn), score "
    "each theme's severity by its impact on activation, set frequency to how many supplied "
    "items express it, and give one concrete, actionable recommendation per theme. Back "
    "every theme with verbatim representative quotes copied from the supplied items — never "
    "invent quotes or feedback that was not provided. Order themes most to least important "
    "(severity, then frequency). If the data is thin, say so in the summary rather than "
    "speculating."
)


# -- model-facing schema: evidence is quote strings only (no provenance the model can't know)


class _LLMTheme(BaseModel):
    title: str = Field(description="Short, specific name for the theme.")
    type: ThemeType = Field(
        description="success = delight / fast activation; failure = confusion / friction; "
        "churn = the user abandoned or switched away."
    )
    severity: Severity = Field(description="Impact on activation: high / medium / low.")
    onboarding_stage: str = Field(
        description="Where it surfaces: signup, setup, first-use, integrations, "
        "pricing-discovery, activation, ..."
    )
    frequency: int = Field(description="How many supplied items express this theme.")
    evidence: List[str] = Field(
        description="Verbatim representative quotes copied from the supplied items. "
        "Never invent quotes."
    )
    recommendation: str = Field(description="Concrete, actionable onboarding change.")


class _LLMReport(BaseModel):
    product: str
    summary: str = Field(
        description="2-4 sentence executive summary of activation strengths and risks."
    )
    themes: List[_LLMTheme]


def _build_user(req: AnalyzeRequest) -> str:
    lines = []
    for i, item in enumerate(req.feedback, 1):
        bits = [b for b in (item.source, item.url) if b]
        tag = f"  [{' | '.join(bits)}]" if bits else ""
        lines.append(f"{i}. {item.text}{tag}")
    return (
        f"Product / category: {req.product}\n\n"
        f"Public feedback items ({len(req.feedback)}):\n"
        + "\n".join(lines)
        + "\n\nProduce the onboarding-intelligence report."
    )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def _ground(llm_report: _LLMReport, req: AnalyzeRequest) -> OnboardingReport:
    index = [(_norm(item.text), item) for item in req.feedback]
    n = len(req.feedback)
    themes: list[Theme] = []
    for t in llm_report.themes:
        kept: list[Evidence] = []
        for quote in t.evidence:
            qn = _norm(quote)
            if not qn:
                continue
            match = next((item for tn, item in index if qn in tn or tn in qn), None)
            if match is None:  # invented / unmatched quote — drop it
                continue
            kept.append(Evidence(quote=quote, source=match.source, url=match.url))
        if not kept:  # theme had no grounded evidence — drop it
            continue
        themes.append(
            Theme(
                title=t.title,
                type=t.type,
                severity=t.severity,
                onboarding_stage=t.onboarding_stage,
                frequency=min(t.frequency, n),  # can't express more often than items exist
                evidence=kept,
                recommendation=t.recommendation,
            )
        )
    return OnboardingReport(product=req.product, summary=llm_report.summary, themes=themes)


def analyze(req: AnalyzeRequest, connector: LLMConnector | None = None) -> OnboardingReport:
    """Run the analysis and return a validated, grounded OnboardingReport."""
    if not req.feedback:
        raise ValueError("No feedback items supplied to analyze.")
    connector = connector or default_connector()
    llm_report = connector.complete_structured(
        system=SYSTEM, user=_build_user(req), schema=_LLMReport
    )
    return _ground(llm_report, req)  # type: ignore[arg-type]
