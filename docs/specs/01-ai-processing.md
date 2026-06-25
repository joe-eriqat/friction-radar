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

Two LLM layers, then deterministic grounding:

1. Reject empty `feedback` with `ValueError` **before** any connector call.
2. **Layer 1 — relevance gate:** `complete_structured(schema=_OffTopic)` returns the indices of
   items that are clearly off-topic (not about the product); drop them. Conservative — only
   removes flagged items; keeps negative/vague/praise/feature-request feedback. If nothing
   survives → `ValueError`.
3. **Layer 2 — theming:** on the kept items, `complete_structured(schema=_LLMReport)` clusters
   into a few sharp themes (strict churn = user left/switched/deleted; single best-fit theme
   per item; one quote per supporting item). Evidence is quote strings only (the model can't
   know provenance).
4. **Ground the evidence:** keep only quotes matching a kept input item; a quote is claimed by
   at most one theme (most-important first) and never duplicated; drop invented / unmatched
   quotes; drop themes left with none; attach the matched item's `source`/`url`; set
   `frequency = len(grounded evidence)`.
5. Overwrite `report.product` with the caller's label; assemble + return the `OnboardingReport`.

## Acceptance criteria

1. Empty `feedback` → `ValueError`, no connector call.
2. Non-empty input → schema-valid report: every theme has a valid `type`/`severity`,
   non-empty `title`/`recommendation`/`onboarding_stage`.
3. `report.product == req.product` exactly.
4. **Grounding (key quality bar):** every `Evidence.quote` matches some input item's `text`
   under normalization (case-insensitive, whitespace-collapsed substring). Invented / unmatched
   quotes are removed; a theme with zero remaining evidence is removed.
5. Each surviving `Evidence` carries the `source`/`url` of the item it matched.
6. **Single assignment:** a quote appears in at most one theme, and never twice within a theme.
7. **`theme.frequency == len(theme.evidence)`** — frequency is *derived* from grounded evidence,
   so the count always matches what's shown (not a model-asserted number).
8. Connector / validation failure → `RuntimeError` wrapping the cause. No silent fallback.
9. **Relevance:** clearly off-topic items (the Layer-1 verdict) do not appear in the report;
   legitimate feedback that merely mentions an unrelated word is kept.

> **Scope of the guarantees.** Grounding enforces *realness*, *single assignment*,
> *de-duplication*, and *frequency = evidence* deterministically. **Relevance and theme
> assignment are model judgments**, isolated into the Layer-1 gate (relevance) and the Layer-2
> theming call (assignment). They are made reliable by running the Connector at low temperature
> (default `0`); raising temperature reintroduces run-to-run noise in both.

## Testing

- **Unit (no network):** fake connector returns a canned `_LLMReport` → assert `product`
  override, prompt contains every item's `text`, `ValueError` on empty input.
- **Grounding unit:** fabricated quote dropped; all-fabricated theme dropped; surviving
  evidence carries provenance.
- **Frequency unit:** `frequency == len(evidence)` after grounding.
- **Single-assignment unit:** a quote offered to two themes lands in only the first; no quote
  appears twice.
- **Relevance-gate unit:** an item flagged off-topic is dropped before theming; all-off-topic
  input raises `ValueError`.
- **Integration (key-gated):** real connector on `data/sample_feedback.json` → schema-valid,
  ≥ 1 theme, all evidence grounded.

## Resolved decisions

- Default model: `openai/gpt-4o-mini` (Connector's concern; see spec 02).
- Strictness: handled entirely in the Connector (strict where supported, else JSON-mode +
  retry-once).
- `frequency` = count of grounded supporting quotes (`len(evidence)`), **derived** — always
  matches the evidence shown, rather than an unverifiable model count. Any % is derived in Output.
- Relevance is a dedicated Layer-1 gate (`_OffTopic` verdict), not just a theming-prompt rule;
  single-best-theme assignment is a Layer-2 judgment. Stability of both depends on low Connector
  temperature (default `0`). Realness, dedup, single assignment, and frequency are enforced
  deterministically in grounding.
