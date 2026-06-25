# Module Spec 02 — LLM Connector

**Status:** accepted (2026-06-25) · **Build order:** 1st (nothing depends on the rest yet)

## Purpose

The **only** module that knows a provider exists. A generic structured-output wrapper over
**LiteLLM**, so every upstream module talks to a small `Protocol` instead of `litellm`/`openai`.
Provider, model, and endpoint are config — direct OpenAI and an OpenAI-compatible gateway run
the identical code path.

## Public interface

```python
class LLMConnector(Protocol):
    def complete_structured(
        self, *, system: str, user: str,
        schema: type[BaseModel], max_tokens: int = 4096,
    ) -> BaseModel: ...          # a validated instance of `schema`

def default_connector() -> LiteLLMConnector   # built from env
```

## In / Out

- **In:** `system`, `user` (prompt strings, built by the caller), `schema` (a Pydantic model
  class), `max_tokens`.
- **Out:** a validated instance of `schema`, or a raised `RuntimeError`.

## Strictness (the core behavior)

Two ways to force the output to match `schema`:

- **Strict structured outputs** — the provider constrains the model at decode time so it
  cannot emit schema-invalid JSON (OpenAI structured outputs). Used where the provider/model
  supports it (`litellm.supports_response_schema`).
- **JSON-mode + validate-and-retry-once** — model told to return JSON (schema injected into
  the prompt); validate after; on failure, send the error back once; then give up.

The caller never knows which path ran.

## Configuration

| Env var | Meaning | Example |
|---|---|---|
| `FRICTION_RADAR_MODEL` | LiteLLM model string | `openai/gpt-4o` (default; `gpt-4o-mini` = cheaper/weaker) |
| `OPENAI_API_KEY` | direct-OpenAI auth | `sk-...` |
| `FRICTION_RADAR_LLM_BASE_URL` | optional OpenAI-compatible endpoint | `http://localhost:19000/v1` |
| `FRICTION_RADAR_TEMPERATURE` | sampling temperature (default `0`) | `0`, or `none` to omit |

Temperature defaults to `0` (near-greedy) so the analytical tasks here — classification and
extraction — are stable run-to-run. (At the provider default ~1.0 the relevance gate flagged a
*different* item each call.) Set `none`/`default` to omit the parameter for models that reject
it (e.g. reasoning models).

## Acceptance criteria

1. Returns a validated `schema` instance — never an unvalidated dict or `None`.
2. Strict where `supports_response_schema(model)`; otherwise JSON-mode + retry-once, then
   `RuntimeError`.
3. Provider/model/endpoint come entirely from config; identical path for direct OpenAI and a
   gateway (only `base_url` differs).
4. Neither `api_key` nor `base_url` set → `RuntimeError` (config) **before** any network call.
5. Network/SDK exception → wrapped in `RuntimeError` with the cause.
6. No provider SDK symbol leaks above this module (callers import only the `Protocol`).
7. `temperature` (when set) is forwarded to the provider; default config sets it to `0`.

## Testing

Monkeypatch the internal `_completion` seam (no litellm needed for unit tests):

- valid JSON (strict) → returns validated instance, one call.
- garbage then valid (JSON-mode) → retry succeeds, exactly two calls.
- garbage twice (JSON-mode) → `RuntimeError`.
- no api_key + no base_url → `RuntimeError`, `_completion` never called.
- `_completion` raises → wrapped `RuntimeError`.
- `temperature` forwarded to `_completion` when set, omitted when `None`.

Integration (key-gated): real call returns a validated instance.
