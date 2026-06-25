"""Unit tests for the LLM Connector (spec 02).

All tests monkeypatch the `_completion` seam, so they run with zero network and do not
require litellm to be installed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app import connector as conn


class Demo(BaseModel):
    name: str
    count: int


def _resp(content: str) -> SimpleNamespace:
    """Build a minimal LiteLLM-shaped response: resp.choices[0].message.content."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_strict_path_returns_validated(monkeypatch):
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return _resp('{"name": "x", "count": 3}')

    monkeypatch.setattr(conn, "_completion", fake)
    c = conn.LiteLLMConnector(model="openai/gpt-4o-mini", api_key="k", strict=True)

    out = c.complete_structured(system="s", user="u", schema=Demo)

    assert isinstance(out, Demo)
    assert out.name == "x" and out.count == 3
    assert len(calls) == 1
    assert calls[0]["response_format"] is Demo  # strict passes the schema through


def test_json_mode_retries_once_then_succeeds(monkeypatch):
    seq = ["not json at all", '{"name": "y", "count": 7}']

    def fake(**kwargs):
        return _resp(seq.pop(0))

    monkeypatch.setattr(conn, "_completion", fake)
    c = conn.LiteLLMConnector(model="local/whatever", api_key="k", strict=False)

    out = c.complete_structured(system="s", user="u", schema=Demo)

    assert out.count == 7
    assert seq == []  # exactly two calls consumed both responses


def test_json_mode_two_failures_raises(monkeypatch):
    def fake(**kwargs):
        return _resp("still not valid json")

    monkeypatch.setattr(conn, "_completion", fake)
    c = conn.LiteLLMConnector(model="local/whatever", api_key="k", strict=False)

    with pytest.raises(RuntimeError):
        c.complete_structured(system="s", user="u", schema=Demo)


def test_missing_config_raises_before_network(monkeypatch):
    called = False

    def fake(**kwargs):
        nonlocal called
        called = True
        return _resp("{}")

    monkeypatch.setattr(conn, "_completion", fake)
    c = conn.LiteLLMConnector(model="openai/gpt-4o-mini", api_key=None, base_url=None)

    with pytest.raises(RuntimeError):
        c.complete_structured(system="s", user="u", schema=Demo)
    assert called is False  # never reached the network


def test_call_failure_is_wrapped(monkeypatch):
    def fake(**kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr(conn, "_completion", fake)
    c = conn.LiteLLMConnector(model="openai/gpt-4o-mini", api_key="k", strict=True)

    with pytest.raises(RuntimeError):
        c.complete_structured(system="s", user="u", schema=Demo)
