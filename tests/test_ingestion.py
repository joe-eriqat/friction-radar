"""Unit tests for Ingestion (spec 03): DemoAdapter + UploadAdapter."""

from __future__ import annotations

import pytest

from app.ingestion import (
    DemoAdapter,
    UploadAdapter,
    _detect_format,
    _looks_messy,
    _Segments,
    available_demos,
    demo_request,
    normalize,
)
from app.schemas import FeedbackItem


# ---- DemoAdapter / normalize ----------------------------------------------------------


def test_demo_adapter_loads_sample():
    items = DemoAdapter().load()
    assert items
    assert all(i.text.strip() for i in items)
    assert all(i.source == "demo" for i in items)


def test_unknown_dataset_raises():
    with pytest.raises(ValueError):
        DemoAdapter().load("bogus")


def test_normalize_strips_dedupes_drops_blanks():
    out = normalize(
        [FeedbackItem(text="  hi  "), FeedbackItem(text="hi"), FeedbackItem(text="   "), FeedbackItem(text="bye")]
    )
    assert [i.text for i in out] == ["hi", "bye"]


def test_demo_request_has_product_and_items():
    req = demo_request()
    assert req.product
    assert req.feedback


def test_available_demos_lists_default():
    demos = available_demos()
    assert demos
    ids = {d["id"] for d in demos}
    assert "default" in ids
    default = next(d for d in demos if d["id"] == "default")
    assert default["name"]
    assert default["count"] > 0


def test_demo_request_by_name_matches_default():
    assert demo_request("default").product == demo_request().product


def test_demo_request_unknown_name_raises():
    with pytest.raises(ValueError):
        demo_request("does-not-exist")


# ---- UploadAdapter --------------------------------------------------------------------


class FakeSegmenter:
    """Stands in for the connector on the messy-text path; returns canned segments."""

    def __init__(self, comments: list[str]) -> None:
        self.comments = comments
        self.calls = 0

    def complete_structured(self, *, system, user, schema, max_tokens=4096):
        self.calls += 1
        return _Segments(comments=self.comments)


def test_csv_picks_text_column():
    raw = "id,rating,comment\n1,5,Loved the setup\n2,2,Pricing was confusing\n"
    items = UploadAdapter().load(raw)
    assert [i.text for i in items] == ["Loved the setup", "Pricing was confusing"]


def test_csv_maps_source_column():
    raw = "platform,comment\nreddit,Great onboarding\napp_store,Too slow to start\n"
    items = UploadAdapter().load(raw)
    assert [(i.source, i.text) for i in items] == [
        ("reddit", "Great onboarding"),
        ("app_store", "Too slow to start"),
    ]


def test_json_list_of_strings():
    items = UploadAdapter().load('["first one", "second one"]')
    assert [i.text for i in items] == ["first one", "second one"]


def test_json_list_of_objects():
    items = UploadAdapter().load('[{"text": "hello", "source": "g2"}, {"comment": "hey"}]')
    assert items[0].text == "hello" and items[0].source == "g2"
    assert items[1].text == "hey" and items[1].source == "upload"


def test_clean_oneperline_no_llm():
    fake = FakeSegmenter([])
    raw = "Loved the setup process.\nPricing was confusing.\nGreat support team!"
    items = UploadAdapter(connector=fake).load(raw, source="pasted")
    assert [i.text for i in items] == ["Loved the setup process.", "Pricing was confusing.", "Great support team!"]
    assert fake.calls == 0  # clean text never touches the model
    assert all(i.source == "pasted" for i in items)


def test_clean_paragraphs_no_llm():
    fake = FakeSegmenter([])
    raw = "First comment that\nwraps over two lines.\n\nSecond comment also\nover two lines."
    items = UploadAdapter(connector=fake).load(raw)
    assert len(items) == 2  # blank-line paragraphs are the unit
    assert fake.calls == 0


def test_messy_routes_to_llm_and_verifies_verbatim():
    fake = FakeSegmenter(
        [
            "Setup was painful and confusing.",          # verbatim — kept
            "A paraphrased line not in the source.",     # not present — dropped
            "Pricing felt sneaky and unclear.",          # verbatim — kept
        ]
    )
    raw = (
        "Feedback export — please review\n"
        "====================\n"
        "Setup was painful and confusing.\n"
        "author: u/someone\n"
        "====================\n"
        "Pricing felt sneaky and unclear.\n"
    )
    items = UploadAdapter(connector=fake).load(raw)
    assert fake.calls == 1  # separator bars -> messy -> LLM
    assert [i.text for i in items] == [
        "Setup was painful and confusing.",
        "Pricing felt sneaky and unclear.",
    ]  # the fabricated/paraphrased segment is dropped by the verbatim guardrail


def test_looks_messy_signals():
    assert _looks_messy("a comment\n====\nanother comment") is True       # separator bar
    assert _looks_messy("Loved it.\nHated the price.\nGreat support.") is False  # clean lines
    assert _looks_messy("author: x\ndate: y\nplatform: z\nreal comment") is True  # metadata-heavy


def test_format_detection_and_empty():
    assert _detect_format('["a","b"]') == "json"
    assert _detect_format("id,comment\n1,hi\n2,bye\n") == "csv"
    assert _detect_format("just some pasted prose.") == "text"
    with pytest.raises(ValueError):
        UploadAdapter().load("   \n  \n")
