"""Output / Report (spec 05): OnboardingReport -> prioritized view + share-ready exports.

Pure functions, no I/O, no model. Themes are prioritized (severity, then frequency) for
presentation; the JSON export stays faithful to the stored report so it round-trips into an
equal OnboardingReport.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel

from .schemas import CommentClassification, OnboardingReport, Severity, Theme

_SEVERITY_RANK = {Severity.high: 0, Severity.medium: 1, Severity.low: 2}
_SEVERITY_LABEL = {Severity.high: "HIGH", Severity.medium: "MEDIUM", Severity.low: "LOW"}


class ReportView(BaseModel):
    """Presentation-ready payload for the SPA: themes prioritized, plus counts."""

    product: str
    summary: str
    theme_count: int
    total_feedback: int = 0
    relevant_count: int = 0
    themes: List[Theme]  # severity (high > medium > low), then frequency desc
    comments: List[CommentClassification] = []  # full per-comment audit (for export, not the page)


def _prioritized(themes: List[Theme]) -> List[Theme]:
    # `sorted` is stable, so ties (same severity + frequency) keep their input order.
    return sorted(themes, key=lambda t: (_SEVERITY_RANK[t.severity], -t.frequency))


def view_model(report: OnboardingReport) -> ReportView:
    themes = _prioritized(report.themes)
    return ReportView(
        product=report.product,
        summary=report.summary,
        theme_count=len(themes),
        total_feedback=report.total_feedback,
        relevant_count=report.relevant_count,
        themes=themes,
        comments=report.comments,
    )


def to_json(report: OnboardingReport) -> str:
    """Canonical serialization — re-imports into an equal OnboardingReport."""
    return report.model_dump_json(indent=2)


def to_markdown(report: OnboardingReport) -> str:
    """Share / screenshot-ready Markdown. Lossless vs the report; themes prioritized."""
    lines: list[str] = [f"# Onboarding Report — {report.product}", ""]
    if report.total_feedback:
        lines.append(
            f"_Analyzed {report.relevant_count} relevant of "
            f"{report.total_feedback} submitted comments._"
        )
        lines.append("")
    lines.append(report.summary.strip() or "_No summary._")
    lines.append("")

    themes = _prioritized(report.themes)
    if not themes:
        lines.append("_No themes found._")
        return "\n".join(lines) + "\n"

    for t in themes:
        lines.append(f"## {t.title}")
        lines.append(
            f"**{t.type.value} · {_SEVERITY_LABEL[t.severity]}** · "
            f"stage: {t.onboarding_stage} · mentioned {t.frequency}×"
        )
        lines.append("")
        lines.append(f"**Recommendation:** {t.recommendation}")
        lines.append("")
        lines.append("Evidence:")
        for ev in t.evidence:
            cite = [p for p in (ev.source, f"[link]({ev.url})" if ev.url else None) if p]
            suffix = f" — {' · '.join(cite)}" if cite else ""
            lines.append(f"- > {ev.quote}{suffix}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
