"""Golden-style tests for Output / Report (spec 05)."""

from __future__ import annotations

from app.output import ReportView, to_json, to_markdown, view_model
from app.schemas import Evidence, OnboardingReport, Severity, Theme, ThemeType


def _theme(title, sev, freq, type_=ThemeType.failure, evidence=None) -> Theme:
    return Theme(
        title=title,
        type=type_,
        severity=sev,
        onboarding_stage="setup",
        frequency=freq,
        evidence=evidence or [Evidence(quote=f"{title} quote")],
        recommendation=f"fix {title}",
    )


def _report(themes, product="P", summary="S") -> OnboardingReport:
    return OnboardingReport(product=product, summary=summary, themes=themes)


def test_prioritized_by_severity_then_frequency_stable():
    themes = [
        _theme("A", Severity.medium, 5),
        _theme("B", Severity.high, 2),
        _theme("C", Severity.high, 9),
        _theme("D", Severity.low, 10),
        _theme("E", Severity.medium, 5),  # ties with A -> must stay after A (stable)
    ]
    view = view_model(_report(themes))
    assert isinstance(view, ReportView)
    assert [t.title for t in view.themes] == ["C", "B", "A", "E", "D"]
    assert view.theme_count == 5


def test_to_json_roundtrips_into_equal_report():
    r = _report(
        [
            _theme(
                "A",
                Severity.high,
                3,
                evidence=[Evidence(quote="q", source="reddit", url="http://x")],
            )
        ]
    )
    again = OnboardingReport.model_validate_json(to_json(r))
    assert again == r  # canonical + faithful (order preserved, no data loss)


def test_markdown_contains_every_field():
    r = _report(
        [
            _theme(
                "Setup pain",
                Severity.high,
                4,
                evidence=[Evidence(quote="setup was awful", source="reddit", url="http://r/1")],
            )
        ],
        product="My App",
        summary="Strong value, rough setup.",
    )
    md = to_markdown(r)
    for needle in [
        "My App",
        "Strong value, rough setup.",
        "Setup pain",
        "failure",
        "HIGH",
        "setup",
        "4",
        "fix Setup pain",
        "setup was awful",
        "reddit",
        "http://r/1",
    ]:
        assert needle in md, f"missing: {needle!r}"


def test_markdown_empty_themes_state():
    md = to_markdown(_report([], product="Empty", summary="No data."))
    assert "Empty" in md
    assert "No data." in md
    assert "No themes found" in md


def test_markdown_evidence_without_provenance_is_clean():
    md = to_markdown(_report([_theme("T", Severity.low, 1, evidence=[Evidence(quote="bare quote")])]))
    assert "- > bare quote" in md  # no dangling " — " separator when no source/url
