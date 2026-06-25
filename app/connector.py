"""LLM Connector — the only module that knows a provider exists.

A generic structured-output wrapper over LiteLLM. Every upstream module depends on the
`LLMConnector` Protocol, never on `litellm`/`openai`. Provider, model, and endpoint are
config, so direct OpenAI and an OpenAI-compatible gateway run the identical code path.

See spec 02 (docs/specs/02-llm-connector.md) for the contract and acceptance criteria.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = "openai/gpt-4o-mini"


class LLMConnector(Protocol):
    """The only interface upstream modules are allowed to import."""

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> BaseModel: ...


# --- seams kept module-level so unit tests can monkeypatch without litellm installed ----


def _completion(**kwargs: Any) -> Any:
    """Thin wrapper over `litellm.completion`. Patched in unit tests."""
    import litellm

    return litellm.completion(**kwargs)


def _supports_strict(model: str) -> bool:
    """True if the provider/model enforces a JSON schema at decode time."""
    try:
        import litellm

        return bool(litellm.supports_response_schema(model=model))
    except Exception:
        return False


def _extract_content(resp: Any) -> str:
    """Pull the assistant message text out of a LiteLLM-shaped response."""
    try:
        return resp.choices[0].message.content
    except (AttributeError, TypeError, KeyError, IndexError):
        return resp["choices"][0]["message"]["content"]


class LiteLLMConnector:
    """Concrete `LLMConnector`. `strict=None` auto-detects per model."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        strict: bool | None = None,
        temperature: float | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self._strict = strict
        self.temperature = temperature

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> BaseModel:
        # AC4: fail on missing config before any network call.
        if not self.api_key and not self.base_url:
            raise RuntimeError(
                "LLM connector misconfigured: set OPENAI_API_KEY or "
                "FRICTION_RADAR_LLM_BASE_URL."
            )
        strict = self._strict if self._strict is not None else _supports_strict(self.model)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if strict:
            return self._strict_call(messages, schema, max_tokens)
        return self._json_mode_call(messages, schema, max_tokens)

    # -- internals ----------------------------------------------------------------------

    def _call(self, *, messages: list[dict], response_format: Any, max_tokens: int) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "response_format": response_format,
            "max_tokens": max_tokens,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            return _completion(**kwargs)
        except Exception as exc:  # AC5: wrap provider/network errors.
            raise RuntimeError(f"LLM request failed: {exc}") from exc

    def _strict_call(
        self, messages: list[dict], schema: type[BaseModel], max_tokens: int
    ) -> BaseModel:
        resp = self._call(messages=messages, response_format=schema, max_tokens=max_tokens)
        content = _extract_content(resp)
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            raise RuntimeError(
                f"Strict output failed validation against {schema.__name__}: {exc}"
            ) from exc

    def _json_mode_call(
        self, messages: list[dict], schema: type[BaseModel], max_tokens: int
    ) -> BaseModel:
        # The schema isn't enforced by the provider here, so describe it in the prompt
        # (this also satisfies OpenAI's "must mention json" json_object requirement).
        schema_hint = (
            "Respond with a single JSON object that conforms exactly to this JSON Schema:\n"
            + json.dumps(schema.model_json_schema())
        )
        base = [
            {"role": "system", "content": messages[0]["content"] + "\n\n" + schema_hint},
            messages[1],
        ]
        attempt_messages = list(base)
        last_error: Exception | None = None
        for _ in range(2):  # initial attempt + one repair
            resp = self._call(
                messages=attempt_messages,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
            )
            content = _extract_content(resp)
            try:
                return schema.model_validate_json(content)
            except (ValidationError, ValueError) as exc:
                last_error = exc
                attempt_messages = base + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            f"That did not match the schema ({exc}). "
                            "Return ONLY valid JSON matching the schema, nothing else."
                        ),
                    },
                ]
        raise RuntimeError(
            f"Model did not return schema-valid JSON for {schema.__name__} "
            f"after one retry: {last_error}"
        ) from last_error


def _env_temperature() -> float | None:
    """Sampling temperature from env (default 0 — near-greedy, for stable categorization).

    Set FRICTION_RADAR_TEMPERATURE to a float, or to "none"/"default" to omit the parameter
    entirely (some models — e.g. reasoning models — reject an explicit temperature).
    """
    raw = os.environ.get("FRICTION_RADAR_TEMPERATURE", "0").strip().lower()
    if raw in ("", "none", "default"):
        return None
    try:
        return float(raw)
    except ValueError:
        return 0.0


def default_connector() -> LiteLLMConnector:
    """Construct the connector from environment config."""
    return LiteLLMConnector(
        model=os.environ.get("FRICTION_RADAR_MODEL", DEFAULT_MODEL),
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("FRICTION_RADAR_LLM_BASE_URL"),
        temperature=_env_temperature(),
    )
