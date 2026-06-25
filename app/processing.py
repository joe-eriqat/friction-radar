"""AI Processing (spec 01): (product, feedback[]) -> grounded OnboardingReport.

Two LLM layers, then deterministic grounding:
  1. RELEVANCE GATE — classify which feedback items are off-topic (not about the product)
     and drop them before theming. A focused, inspectable filter; the theming model never
     sees the noise.
  2. THEMING — cluster the on-topic feedback into themes; evidence is quote strings only.
Then GROUND each quote against the (kept) input items: drop invented / unmatched quotes,
enforce single assignment (a quote belongs to at most one theme), de-duplicate, attach the
matched item's source/url, and set frequency = count of grounded quotes. Provider/SDK
details live in the LLM Connector.
"""

from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, Field

from .connector import LLMConnector, default_connector
from .schemas import AnalyzeRequest, Evidence, FeedbackItem, OnboardingReport, Severity, Theme, ThemeType

# ---- Layer 1: relevance gate ----------------------------------------------------------

RELEVANCE_SYSTEM = (
    "You are a relevance filter for product feedback. You are given a PRODUCT and a numbered "
    "list of feedback items. Flag an item as OFF-TOPIC only when it is clearly not about this "
    "product or its category — for example it talks about an unrelated business, place, or "
    "subject, or explicitly states it is unrelated. Do NOT flag an item merely for being "
    "negative, vague, brief, praise, or a feature request — those are on-topic. Return the "
    "1-based indices of the clearly off-topic items (empty list if none)."
)


class _OffTopic(BaseModel):
    offtopic_indices: List[int] = Field(
        description="1-based indices of feedback items that are clearly NOT about this product "
        "(off-topic noise). Empty if every item is on-topic."
    )


def _relevance_user(req: AnalyzeRequest) -> str:
    lines = [f"{i}. {item.text}" for i, item in enumerate(req.feedback, 1)]
    return (
        f"Product / category: {req.product}\n\n"
        f"Feedback items ({len(req.feedback)}):\n"
        + "\n".join(lines)
        + "\n\nList the indices of the clearly off-topic items."
    )


def _relevant_items(req: AnalyzeRequest, connector: LLMConnector) -> List[FeedbackItem]:
    """Drop off-topic feedback before theming. Conservative: only removes flagged items."""
    verdict: _OffTopic = connector.complete_structured(  # type: ignore[assignment]
        system=RELEVANCE_SYSTEM, user=_relevance_user(req), schema=_OffTopic
    )
    drop = {i for i in verdict.offtopic_indices if 1 <= i <= len(req.feedback)}
    return [item for n, item in enumerate(req.feedback, 1) if n not in drop]


# ---- Layer 2: theming -----------------------------------------------------------------

SYSTEM = (
    "You are an onboarding-intelligence analyst. You read public customer feedback about a "
    "product and surface where users succeed or struggle during onboarding and early "
    "activation.\n\n"
    "Follow these rules:\n"
    "- THEMES: Cluster related feedback into a small set of clearly distinct themes. Aim for "
    "the few sharpest themes and merge near-duplicates rather than splitting hairs. Each theme "
    "is success (delight / fast activation), failure (confusion / friction / unmet "
    "expectations), or churn. Use churn ONLY when the language shows the user stopped using, "
    "switched away, deleted, or uninstalled the product.\n"
    "- ASSIGNMENT: Put each feedback item under the single theme it fits best. Never repeat the "
    "same quote across themes, and only include a quote that genuinely supports its theme.\n"
    "- EVIDENCE: Back each theme with quotes copied verbatim from the supplied items — include "
    "one quote for every item that expresses the theme. Never invent or paraphrase.\n"
    "- Give each theme a concrete, actionable onboarding recommendation and score its severity "
    "by impact on activation. Order themes most to least important. If the data is thin, say so "
    "in the summary instead of padding with weak themes."
)


class _LLMTheme(BaseModel):
    title: str = Field(description="Short, specific name for the theme.")
    type: ThemeType = Field(
        description="success = delight / fast activation; failure = confusion / friction; "
        "churn = the user stopped using, switched away, deleted, or uninstalled."
    )
    severity: Severity = Field(description="Impact on activation: high / medium / low.")
    onboarding_stage: str = Field(
        description="Where it surfaces: signup, setup, first-use, integrations, "
        "pricing-discovery, activation, ..."
    )
    evidence: List[str] = Field(
        description="Verbatim quotes copied exactly from the supplied items — one for every "
        "item that expresses this theme. Never invented or paraphrased."
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
    used: set[str] = set()  # a quote belongs to at most one theme (most-important first)
    themes: list[Theme] = []
    for t in llm_report.themes:
        kept: list[Evidence] = []
        for quote in t.evidence:
            qn = _norm(quote)
            if not qn or qn in used:  # empty, or already claimed by an earlier theme / dup
                continue
            match = next((item for tn, item in index if qn in tn or tn in qn), None)
            if match is None:  # invented / off-topic / otherwise unmatched — drop it
                continue
            used.add(qn)
            kept.append(Evidence(quote=quote, source=match.source, url=match.url))
        if not kept:  # theme with no grounded evidence — drop it
            continue
        themes.append(
            Theme(
                title=t.title,
                type=t.type,
                severity=t.severity,
                onboarding_stage=t.onboarding_stage,
                frequency=len(kept),  # derived — always matches the evidence shown
                evidence=kept,
                recommendation=t.recommendation,
            )
        )
    return OnboardingReport(product=req.product, summary=llm_report.summary, themes=themes)


def analyze(req: AnalyzeRequest, connector: LLMConnector | None = None) -> OnboardingReport:
    """Filter off-topic noise, theme the rest, and return a grounded OnboardingReport."""
    if not req.feedback:
        raise ValueError("No feedback items supplied to analyze.")
    connector = connector or default_connector()

    kept = _relevant_items(req, connector)  # Layer 1
    if not kept:
        raise ValueError("No on-topic feedback to analyze.")
    scoped = (
        req
        if len(kept) == len(req.feedback)
        else AnalyzeRequest(product=req.product, feedback=kept)
    )

    llm_report = connector.complete_structured(  # Layer 2
        system=SYSTEM, user=_build_user(scoped), schema=_LLMReport
    )
    return _ground(llm_report, scoped)  # type: ignore[arg-type]
