"""Unit tests for AI Processing (spec 01) — fake connector, zero network.

`analyze` now makes two connector calls: the relevance gate (schema `_OffTopic`) then the
theming call (schema `_LLMReport`). The fake dispatches on the requested schema.
"""

from __future__ import annotations

import pytest

from app.processing import _LLMReport, _LLMTheme, _OffTopic, analyze
from app.schemas import AnalyzeRequest, FeedbackItem, OnboardingReport


class FakeConnector:
    """Returns a canned _OffTopic for the gate and a canned _LLMReport for theming."""

    def __init__(self, report: _LLMReport, offtopic_indices=()) -> None:
        self.report = report
        self.offtopic = list(offtopic_indices)
        self.calls: list[dict] = []

    def complete_structured(self, *, system, user, schema, max_tokens=4096):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if schema is _OffTopic:
            return _OffTopic(offtopic_indices=self.offtopic)
        return self.report

    def theming_user(self) -> str:
        return [c for c in self.calls if c["schema"] is _LLMReport][0]["user"]


def _req() -> AnalyzeRequest:
    return AnalyzeRequest(
        product="My Product",
        feedback=[
            FeedbackItem(text="Setup was painful and confusing", source="reddit", url="http://r/1"),
            FeedbackItem(text="The summary showed up automatically and I loved it"),
        ],
    )


def _theme(title: str, quotes: list[str]) -> _LLMTheme:
    return _LLMTheme(
        title=title,
        type="failure",
        severity="high",
        onboarding_stage="setup",
        evidence=quotes,
        recommendation="do x",
    )


def test_empty_feedback_raises_without_connector_call():
    fake = FakeConnector(_LLMReport(product="x", summary="s", themes=[]))
    with pytest.raises(ValueError):
        analyze(AnalyzeRequest(product="x", feedback=[]), connector=fake)
    assert fake.calls == []  # neither gate nor theming ran


def test_product_override_and_theming_prompt_contains_items():
    fake = FakeConnector(
        _LLMReport(product="MODEL REPHRASED", summary="s", themes=[_theme("Setup", ["Setup was painful"])])
    )
    out = analyze(_req(), connector=fake)
    assert isinstance(out, OnboardingReport)
    assert out.product == "My Product"  # caller's label wins
    user = fake.theming_user()
    assert "Setup was painful and confusing" in user
    assert "The summary showed up automatically and I loved it" in user


def test_grounding_drops_fabricated_and_attaches_provenance():
    fake = FakeConnector(
        _LLMReport(product="p", summary="s",
                   themes=[_theme("Setup", ["Setup was painful", "We adored the onboarding wizard"])])
    )
    out = analyze(_req(), connector=fake)
    assert [e.quote for e in out.themes[0].evidence] == ["Setup was painful"]  # fabricated dropped
    ev = out.themes[0].evidence[0]
    assert ev.source == "reddit" and ev.url == "http://r/1"  # provenance attached


def test_theme_dropped_when_all_evidence_ungrounded():
    fake = FakeConnector(
        _LLMReport(product="p", summary="s",
                   themes=[_theme("Real", ["Setup was painful"]),
                           _theme("Hallucinated", ["a totally invented quote"])])
    )
    out = analyze(_req(), connector=fake)
    assert [t.title for t in out.themes] == ["Real"]


def test_frequency_equals_grounded_evidence_count():
    fake = FakeConnector(
        _LLMReport(product="p", summary="s", themes=[_theme("Both", [
            "Setup was painful",
            "The summary showed up automatically and I loved it",
            "an invented quote that matches nothing",
        ])])
    )
    out = analyze(_req(), connector=fake)
    t = out.themes[0]
    assert t.frequency == len(t.evidence) == 2


def test_quote_used_in_only_one_theme():
    fake = FakeConnector(
        _LLMReport(product="p", summary="s", themes=[
            _theme("First", ["Setup was painful"]),
            _theme("Second", ["Setup was painful", "The summary showed up automatically and I loved it"]),
        ])
    )
    out = analyze(_req(), connector=fake)
    assert [e.quote for e in out.themes[0].evidence] == ["Setup was painful"]
    assert [e.quote for e in out.themes[1].evidence] == ["The summary showed up automatically and I loved it"]
    all_quotes = [e.quote for t in out.themes for e in t.evidence]
    assert len(all_quotes) == len(set(all_quotes))


def test_relevance_gate_drops_offtopic_before_theming():
    # gate flags item 2 as off-topic -> the theming call must not see it
    fake = FakeConnector(
        _LLMReport(product="p", summary="s", themes=[_theme("Setup", ["Setup was painful"])]),
        offtopic_indices=[2],
    )
    analyze(_req(), connector=fake)
    user = fake.theming_user()
    assert "Setup was painful and confusing" in user
    assert "The summary showed up automatically and I loved it" not in user  # filtered out


def test_relevance_gate_all_offtopic_raises():
    fake = FakeConnector(
        _LLMReport(product="p", summary="s", themes=[]),
        offtopic_indices=[1, 2],
    )
    with pytest.raises(ValueError):
        analyze(_req(), connector=fake)
    assert all(c["schema"] is not _LLMReport for c in fake.calls)  # theming never ran
