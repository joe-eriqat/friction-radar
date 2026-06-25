"""Unit tests for AI Processing (spec 01) — fake connector, zero network."""

from __future__ import annotations

import pytest

from app.processing import _LLMReport, _LLMTheme, analyze
from app.schemas import AnalyzeRequest, FeedbackItem, OnboardingReport


class FakeConnector:
    """Returns a canned _LLMReport and records the call."""

    def __init__(self, report: _LLMReport) -> None:
        self.report = report
        self.calls: list[dict] = []

    def complete_structured(self, *, system, user, schema, max_tokens=4096):
        self.calls.append({"system": system, "user": user, "schema": schema})
        return self.report


def _req() -> AnalyzeRequest:
    return AnalyzeRequest(
        product="My Product",
        feedback=[
            FeedbackItem(text="Setup was painful and confusing", source="reddit", url="http://r/1"),
            FeedbackItem(text="The summary showed up automatically and I loved it"),
        ],
    )


def _theme(title: str, quotes: list[str], freq: int = 1) -> _LLMTheme:
    return _LLMTheme(
        title=title,
        type="failure",
        severity="high",
        onboarding_stage="setup",
        frequency=freq,
        evidence=quotes,
        recommendation="do x",
    )


def test_empty_feedback_raises_without_connector_call():
    fake = FakeConnector(_LLMReport(product="x", summary="s", themes=[]))
    with pytest.raises(ValueError):
        analyze(AnalyzeRequest(product="x", feedback=[]), connector=fake)
    assert fake.calls == []  # never called the model


def test_product_override_and_prompt_contains_items():
    fake = FakeConnector(
        _LLMReport(
            product="MODEL REPHRASED",
            summary="s",
            themes=[_theme("Setup", ["Setup was painful"])],
        )
    )
    out = analyze(_req(), connector=fake)
    assert isinstance(out, OnboardingReport)
    assert out.product == "My Product"  # caller's label wins
    user = fake.calls[0]["user"]
    assert "Setup was painful and confusing" in user
    assert "The summary showed up automatically and I loved it" in user


def test_grounding_drops_fabricated_and_attaches_provenance():
    fake = FakeConnector(
        _LLMReport(
            product="p",
            summary="s",
            themes=[_theme("Setup", ["Setup was painful", "We adored the onboarding wizard"])],
        )
    )
    out = analyze(_req(), connector=fake)
    quotes = [e.quote for e in out.themes[0].evidence]
    assert quotes == ["Setup was painful"]  # fabricated quote dropped
    ev = out.themes[0].evidence[0]
    assert ev.source == "reddit" and ev.url == "http://r/1"  # provenance attached


def test_theme_dropped_when_all_evidence_ungrounded():
    fake = FakeConnector(
        _LLMReport(
            product="p",
            summary="s",
            themes=[
                _theme("Real", ["Setup was painful"]),
                _theme("Hallucinated", ["a totally invented quote"]),
            ],
        )
    )
    out = analyze(_req(), connector=fake)
    assert [t.title for t in out.themes] == ["Real"]


def test_frequency_clamped_to_input_size():
    fake = FakeConnector(
        _LLMReport(
            product="p",
            summary="s",
            themes=[_theme("Setup", ["Setup was painful"], freq=99)],
        )
    )
    out = analyze(_req(), connector=fake)
    assert out.themes[0].frequency == 2  # len(feedback) == 2
