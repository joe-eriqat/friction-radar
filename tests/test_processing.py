"""Unit tests for AI Processing (spec 01) — fake connector, zero network.

`analyze` makes two connector calls: the relevance gate (schema `_OffTopic`) then the
index-based classifier (schema `_Classification`). The fake dispatches on the schema.
"""

from __future__ import annotations

import pytest

from app.processing import (
    SAMPLE_QUOTES,
    _Category,
    _Classification,
    _OffTopic,
    analyze,
)
from app.schemas import AnalyzeRequest, FeedbackItem, OnboardingReport


class FakeConnector:
    """Returns a canned _OffTopic for the gate and a canned _Classification for the classifier."""

    def __init__(self, classification: _Classification, offtopic_indices=()) -> None:
        self.classification = classification
        self.offtopic = list(offtopic_indices)
        self.calls: list[dict] = []

    def complete_structured(self, *, system, user, schema, max_tokens=4096):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if schema is _OffTopic:
            return _OffTopic(offtopic_indices=self.offtopic)
        return self.classification

    def classify_user(self) -> str:
        return [c for c in self.calls if c["schema"] is _Classification][0]["user"]


def _items(*texts: str) -> list[FeedbackItem]:
    return [FeedbackItem(text=t, source="pasted") for t in texts]


def _cat(title: str, indices: list[int], type_: str = "failure") -> _Category:
    return _Category(
        title=title,
        type=type_,
        severity="high",
        onboarding_stage="setup",
        recommendation="do x",
        member_indices=indices,
    )


def test_comments_audit_covers_every_input_with_relevance_and_theme():
    # 6 comments; gate drops #2 and #4; classifier assigns a+e to Setup, c to Pricing,
    # leaving f relevant-but-unassigned.
    req = AnalyzeRequest(product="P", feedback=_items("a", "b", "c", "d", "e", "f"))
    fake = FakeConnector(
        _Classification(summary="s", categories=[
            _cat("Setup", [1, 3]),                       # kept-indices -> a, e
            _cat("Pricing", [2], type_="churn"),         # kept-index  -> c
        ]),
        offtopic_indices=[2, 4],                         # b, d dropped
    )
    out = analyze(req, connector=fake)
    audit = [(c.text, c.relevant, c.theme) for c in out.comments]
    assert audit == [
        ("a", True, "Setup"),
        ("b", False, None),     # off-topic
        ("c", True, "Pricing"),
        ("d", False, None),     # off-topic
        ("e", True, "Setup"),
        ("f", True, None),      # relevant but unassigned by the classifier
    ]
    # the audit accounts for every submitted comment, and relevance lines up with the count
    assert len(out.comments) == out.total_feedback == 6
    assert sum(c.relevant for c in out.comments) == out.relevant_count == 4


def test_empty_feedback_raises_without_connector_call():
    fake = FakeConnector(_Classification(summary="s", categories=[]))
    with pytest.raises(ValueError):
        analyze(AnalyzeRequest(product="x", feedback=[]), connector=fake)
    assert fake.calls == []


def test_product_override_and_counts():
    req = AnalyzeRequest(product="My Product", feedback=_items("a", "b", "c"))
    fake = FakeConnector(
        _Classification(summary="s", categories=[_cat("T", [1, 2, 3])])
    )
    out = analyze(req, connector=fake)
    assert isinstance(out, OnboardingReport)
    assert out.product == "My Product"
    assert out.total_feedback == 3 and out.relevant_count == 3
    assert out.themes[0].frequency == 3


def test_frequency_is_real_count_evidence_is_sampled():
    req = AnalyzeRequest(product="P", feedback=_items("a1", "a2", "a3", "a4", "a5", "b1", "b2"))
    fake = FakeConnector(
        _Classification(summary="s", categories=[_cat("A", [1, 2, 3, 4, 5]), _cat("B", [6, 7])])
    )
    out = analyze(req, connector=fake)
    a, b = out.themes
    assert a.frequency == 5 and len(a.evidence) == SAMPLE_QUOTES  # count != shown sample
    assert [e.quote for e in a.evidence] == ["a1", "a2", "a3"]    # first members sampled
    assert b.frequency == 2 and len(b.evidence) == 2


def test_index_used_in_only_one_theme():
    req = AnalyzeRequest(product="P", feedback=_items("x", "y", "z"))
    fake = FakeConnector(
        _Classification(summary="s", categories=[_cat("First", [1, 2]), _cat("Second", [2, 3])])
    )
    out = analyze(req, connector=fake)
    assert out.themes[0].frequency == 2  # claims 1, 2
    assert out.themes[1].frequency == 1  # only 3 left (2 already used)
    assert [e.quote for e in out.themes[1].evidence] == ["z"]


def test_out_of_range_indices_dropped_and_empty_theme_removed():
    req = AnalyzeRequest(product="P", feedback=_items("x", "y"))
    fake = FakeConnector(
        _Classification(summary="s", categories=[_cat("Keep", [1, 99]), _cat("Gone", [42])])
    )
    out = analyze(req, connector=fake)
    assert [t.title for t in out.themes] == ["Keep"]  # bogus indices dropped, empty theme removed
    assert out.themes[0].frequency == 1               # only index 1 was valid
    assert [e.quote for e in out.themes[0].evidence] == ["x"]


def test_provenance_carried_from_corpus():
    req = AnalyzeRequest(
        product="P",
        feedback=[FeedbackItem(text="hi", source="reddit", url="http://r/1")],
    )
    fake = FakeConnector(_Classification(summary="s", categories=[_cat("T", [1])]))
    ev = analyze(req, connector=fake).themes[0].evidence[0]
    assert ev.quote == "hi" and ev.source == "reddit" and ev.url == "http://r/1"


def test_relevance_gate_drops_offtopic_before_classify():
    req = AnalyzeRequest(product="P", feedback=_items("on topic one", "OFF TOPIC noise", "on topic two"))
    # gate flags index 2 off-topic; classifier then sees only the 2 kept items (renumbered)
    fake = FakeConnector(
        _Classification(summary="s", categories=[_cat("T", [1, 2])]),
        offtopic_indices=[2],
    )
    out = analyze(req, connector=fake)
    assert out.total_feedback == 3 and out.relevant_count == 2
    assert "OFF TOPIC noise" not in fake.classify_user()
    assert sorted(e.quote for e in out.themes[0].evidence) == ["on topic one", "on topic two"]


def test_relevance_gate_all_offtopic_raises():
    req = AnalyzeRequest(product="P", feedback=_items("a", "b"))
    fake = FakeConnector(_Classification(summary="s", categories=[]), offtopic_indices=[1, 2])
    with pytest.raises(ValueError):
        analyze(req, connector=fake)
    assert all(c["schema"] is not _Classification for c in fake.calls)  # classifier never ran
