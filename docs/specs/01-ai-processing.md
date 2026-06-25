# Module Spec 01 — AI Processing (inference)

**Status:** accepted (2026-06-25) · **Build order:** 2nd (after LLM Connector) · **Depends on:** spec 02

## Purpose

Turn a product label + a list of public feedback items into a single validated,
**grounded** `OnboardingReport`. This module owns the *prompt* and the *output contract*,
and it verifies that the model's evidence is real. It does **not** own provider/SDK
details (→ LLM Connector) or source parsing (→ Ingestion).

## Public interface

```python
def analyze(req: AnalyzeRequest, connector: LLMConnector | None = None) -> OnboardingReport
```

- `connector=None` → build the default connector from config (`connector.default_connector()`).
- Injectable connector → tests run with a fake, zero network.

## In / Out

- **In:** `AnalyzeRequest { product: str, feedback: list[FeedbackItem] }`.
- **Out:** `OnboardingReport { product, summary, themes: list[Theme] }`, validated + grounded.

Requires the schema change in spec 00: `AnalyzeRequest.feedback` becomes `list[FeedbackItem]`
and `Theme.evidence` becomes `list[Evidence]` (`{quote, source?, url?}`). Severity enum stays
`high|medium|low` (matches existing `schemas.py`). These edits land when this module is built.

## Behavior

1. Reject empty `feedback` with `ValueError` **before** calling the connector.
2. Compose the prompt: system = analyst instructions; user = product label + numbered item
   `text`, with `source`/`url` shown where present so quotes can be cited.
3. `connector.complete_structured(system, user, schema=OnboardingReport)`.
4. Overwrite `report.product` with the caller's label (the model may rephrase it).
5. **Ground the evidence** (see AC4): drop invented quotes; drop themes left with none.
6. **Clamp** each `theme.frequency` to `len(feedback)`.
7. Return the validated report.

## Acceptance criteria

1. Empty `feedback` → `ValueError`, no connector call.
2. Non-empty input → schema-valid report: every theme has a valid `type`/`severity`,
   non-empty `title`/`recommendation`/`onboarding_stage`, `frequency ≥ 1`.
3. `report.product == req.product` exactly.
4. **Grounding (key quality bar):** every `Evidence.quote` matches some input item's `text`
   under normalization (case-insensitive, whitespace-collapsed substring). Ungrounded quotes
   are removed; a theme with zero remaining evidence is removed. No invented quotes survive.
5. Each surviving `Evidence` carries the `source`/`url` of the item it matched.
6. `theme.frequency ≤ len(feedback)` for every theme.
7. Connector / validation failure → `RuntimeError` wrapping the cause. No silent fallback,
   no partial report.

## Testing

- **Unit (no network):** fake connector returns a canned report → assert `product` override,
  prompt contains every item's `text`, `ValueError` on empty input.
- **Grounding unit:** fake report mixes one real and one fabricated quote → fabricated quote
  is dropped; a theme that was all-fabricated is dropped.
- **Integration (key-gated):** real connector on `data/sample_feedback.json` → schema-valid,
  ≥ 1 theme, all evidence grounded.

## Resolved decisions

- Default model: `openai/gpt-4o-mini` (Connector's concern; see spec 02).
- Strictness: handled entirely in the Connector (strict where supported, else JSON-mode +
  retry-once).
- `frequency`: raw count. Any % is derived downstream in Output.
