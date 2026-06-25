"""Unit tests for Ingestion / DemoAdapter (spec 03)."""

from __future__ import annotations

import pytest

from app.ingestion import DemoAdapter, demo_request, normalize
from app.schemas import FeedbackItem


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
        [
            FeedbackItem(text="  hi  "),
            FeedbackItem(text="hi"),
            FeedbackItem(text="   "),
            FeedbackItem(text="bye"),
        ]
    )
    assert [i.text for i in out] == ["hi", "bye"]


def test_demo_request_has_product_and_items():
    req = demo_request()
    assert req.product
    assert req.feedback
