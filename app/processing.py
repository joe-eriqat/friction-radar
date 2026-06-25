"""AI Processing (spec 01): (product, feedback[]) -> OnboardingReport.

Index-based pipeline — the model references items by number, never regenerates their text:

  1. RELEVANCE GATE (LLM) — flag clearly off-topic items and drop them. The kept items are
     numbered 1..N; N is a deterministic count used to gauge coverage afterwards.
  2. CLASSIFIER (LLM) — group the numbered corpus into categories, each carrying the *indices*
     of its member items (+ title/type/severity/stage/recommendation). The model emits indices,
     not quotes, so it cannot invent evidence and cannot under-report counts.
  3. DETERMINISTIC ASSEMBLE — validate indices (in range, single assignment), set each theme's
     frequency to its real member count, attach a representative *sample* of the members'
     quotes (with provenance), and record total_feedback / relevant_count.

No substring grounding is needed: an index either points at a real stored item or it doesn't.
Provider/SDK details live in the LLM Connector.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .connector import LLMConnector, default_connector
from .schemas import AnalyzeRequest, Evidence, FeedbackItem, OnboardingReport, Severity, Theme, ThemeType

SAMPLE_QUOTES = 3  # representative quotes shown per theme (frequency stays the full member count)

# ---- Layer 1: relevance gate ----------------------------------------------------------

RELEVANCE_SYSTEM = (
    "You are a relevance filter. You are given a PRODUCT description and a numbered list of "
    "feedback items. Decide, for each item, whether it is about THIS product.\n\n"
    "ON-TOPIC: the author's own experience with this product — its features, setup, pricing, "
    "support, results, or a direct comparison with alternatives they are choosing between.\n"
    "OFF-TOPIC: general commentary about the subject area that does not concern this product; "
    "opinions, advice, or musings aimed at other people or at the topic at large; or anything "
    "about a different product, business, place, or subject. An item is off-topic even when it "
    "shares the same domain, jargon, or vocabulary as the product — sharing a topic is not the "
    "same as being about this product.\n\n"
    "Do NOT flag an item just for being negative, vague, brief, or a feature request — those are "
    "on-topic when they are about this product. Return the 1-based indices of the off-topic items "
    "(empty list if none). This must work for any kind of product — software, hardware, services, "
    "or consumer goods — so judge purely by whether the feedback is about the given product."
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
    """Drop off-topic feedback. Conservative: only removes flagged items."""
    verdict: _OffTopic = connector.complete_structured(  # type: ignore[assignment]
        system=RELEVANCE_SYSTEM, user=_relevance_user(req), schema=_OffTopic
    )
    drop = {i for i in verdict.offtopic_indices if 1 <= i <= len(req.feedback)}
    return [item for n, item in enumerate(req.feedback, 1) if n not in drop]


# ---- Layer 2: classifier (references items by index, never by text) -------------------

CLASSIFY_SYSTEM = (
    "You are an onboarding-intelligence analyst. You are given a PRODUCT and a numbered list of "
    "on-topic customer feedback items. Group them into a small set of clearly distinct themes — "
    "each theme is success (delight / fast activation), failure (confusion / friction / unmet "
    "expectations), or churn (the user stopped using, switched away, deleted, or uninstalled).\n\n"
    "Rules:\n"
    "- Reference items ONLY by their index number. Never quote, copy, paraphrase, or rewrite "
    "item text.\n"
    "- Assign EVERY item to exactly one theme — the single best fit. Do not list an index under "
    "more than one theme, and do not invent indices that aren't in the list.\n"
    "- Aim for a few sharp themes and merge near-duplicates. Order themes most to least "
    "important.\n"
    "- Give each theme a concrete, actionable onboarding recommendation and a severity (impact "
    "on activation)."
)


class _Category(BaseModel):
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
    recommendation: str = Field(description="Concrete, actionable onboarding change.")
    member_indices: List[int] = Field(
        description="1-based indices of the feedback items that belong to this theme."
    )


class _Classification(BaseModel):
    summary: str = Field(
        description="2-4 sentence executive summary of activation strengths and risks."
    )
    categories: List[_Category]


def _classify_user(items: List[FeedbackItem], product: str) -> str:
    lines = [f"{i}. {item.text}" for i, item in enumerate(items, 1)]
    return (
        f"Product / category: {product}\n\n"
        f"On-topic feedback items ({len(items)}):\n"
        + "\n".join(lines)
        + "\n\nGroup these into themes; reference each item by its index number."
    )


# ---- deterministic assemble -----------------------------------------------------------


def _assemble(
    classification: _Classification, kept: List[FeedbackItem], req: AnalyzeRequest
) -> OnboardingReport:
    n = len(kept)
    used: set[int] = set()  # each index belongs to one theme (most-important first)
    themes: list[Theme] = []
    for cat in classification.categories:
        members: list[FeedbackItem] = []
        for i in cat.member_indices:
            if 1 <= i <= n and i not in used:  # in range + not already claimed
                used.add(i)
                members.append(kept[i - 1])
        if not members:  # theme with no valid members — drop it
            continue
        evidence = [Evidence(quote=m.text, source=m.source, url=m.url) for m in members[:SAMPLE_QUOTES]]
        themes.append(
            Theme(
                title=cat.title,
                type=cat.type,
                severity=cat.severity,
                onboarding_stage=cat.onboarding_stage,
                frequency=len(members),  # real count of assigned items
                evidence=evidence,       # a representative sample of them
                recommendation=cat.recommendation,
            )
        )
    return OnboardingReport(
        product=req.product,
        summary=classification.summary,
        themes=themes,
        total_feedback=len(req.feedback),
        relevant_count=n,
    )


def analyze(req: AnalyzeRequest, connector: LLMConnector | None = None) -> OnboardingReport:
    """Filter off-topic noise, classify the rest by index, and assemble the report."""
    if not req.feedback:
        raise ValueError("No feedback items supplied to analyze.")
    connector = connector or default_connector()

    kept = _relevant_items(req, connector)  # Layer 1
    if not kept:
        raise ValueError("No on-topic feedback to analyze.")

    classification = connector.complete_structured(  # Layer 2
        system=CLASSIFY_SYSTEM, user=_classify_user(kept, req.product), schema=_Classification
    )
    return _assemble(classification, kept, req)  # type: ignore[arg-type]
