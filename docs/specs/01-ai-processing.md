# Module Spec 01 — AI Processing (inference)

**Status:** accepted (2026-06-25, index-based rework) · **Build order:** 2nd · **Depends on:** spec 02

## Purpose

Turn a product label + a list of public feedback items into a single validated
`OnboardingReport`. The model makes only two narrow judgments — *is this relevant?* and *which
theme?* — referencing items **by index**. Everything else (counting, sampling, ordering) is
deterministic code. It does **not** own provider/SDK details (→ LLM Connector) or source
parsing (→ Ingestion).

## Public interface

```python
def analyze(req: AnalyzeRequest, connector: LLMConnector | None = None) -> OnboardingReport
```

- `connector=None` → default connector from config. Injectable connector → tests with a fake.

## In / Out

- **In:** `AnalyzeRequest { product: str, feedback: list[FeedbackItem] }`.
- **Out:** `OnboardingReport { product, summary, themes: list[Theme], total_feedback, relevant_count }`.

`Theme.evidence` is `list[Evidence]` (`{quote, source?, url?}`). `Theme.frequency` is the **real
count** of items assigned to the theme; `evidence` is a representative *sample* (≤ `SAMPLE_QUOTES`).

## Why index-based (the core design)

The model **references items by their number, never regenerates their text.** This:
- makes invented quotes impossible (an index points at a stored item or it doesn't),
- makes counts real and deterministic (frequency = number of indices assigned),
- gives full coverage (every relevant item gets assigned, not a sample the model felt like
  typing out), and
- replaces fuzzy substring grounding with an exact in-range index check.

## Behavior

Two LLM layers, then deterministic assemble:

1. Reject empty `feedback` with `ValueError` **before** any connector call.
2. **Layer 1 — relevance gate:** `complete_structured(schema=_OffTopic)` returns the indices of
   clearly off-topic items; drop them. Conservative (keeps negative/vague/praise/feature
   requests). The kept items are renumbered `1..N`; `N` is the deterministic coverage baseline.
   If `N == 0` → `ValueError`.
3. **Layer 2 — classifier:** `complete_structured(schema=_Classification)` groups the numbered
   corpus into categories, each carrying `member_indices` (+ title/type/severity/stage/
   recommendation). The model emits **indices, not quotes**.
4. **Deterministic assemble:** for each category, keep in-range indices not already used by an
   earlier (more-important) theme (single assignment); drop empty themes; set
   `frequency = len(members)`; build `evidence` from the first `SAMPLE_QUOTES` members' text +
   provenance; record `total_feedback` and `relevant_count = N`.
5. Overwrite `report.product` with the caller's label; return.

## Acceptance criteria

1. Empty `feedback` → `ValueError`, no connector call.
2. Schema-valid report: valid `type`/`severity`, non-empty `title`/`recommendation`/`stage`.
3. `report.product == req.product`; `total_feedback == len(req.feedback)`; `relevant_count == N`.
4. **Relevance:** clearly off-topic items (Layer-1 verdict) are removed before classification and
   never appear; legitimate feedback that merely mentions an unrelated word is kept.
5. **Index integrity:** out-of-range indices are dropped; an index is assigned to at most one
   theme; a theme with no valid members is dropped.
6. **Frequency = real count:** `theme.frequency == len(assigned members)` (not `len(evidence)`);
   `evidence` is a sample of ≤ `SAMPLE_QUOTES` of those members, each carrying its `source`/`url`.
7. Coverage is observable: `sum(theme.frequency) ≤ relevant_count` (unassigned items surface as
   the gap).
8. Connector / validation failure → `RuntimeError`. No silent fallback.

> **Scope of the guarantees.** Index integrity, single assignment, real counts, and provenance
> are enforced deterministically. **Relevance and which-theme are model judgments**, isolated
> into the two layers and made stable by low Connector temperature (default `0`). Index-based
> referencing fixes the *bookkeeping* (counts, coverage, no hallucinated quotes); it does not
> make the *clustering* smarter — theme quality is still a model call.

## Testing

- **Unit (no network, fake connector dispatching on schema):** empty → `ValueError`, no calls;
  product override + `total_feedback`/`relevant_count`; frequency = member count while evidence
  is sampled; single assignment across categories; out-of-range indices dropped + empty theme
  removed; provenance carried from the corpus; relevance gate drops off-topic before classify;
  all-off-topic → `ValueError`.
- **Integration (key-gated):** real connector on `data/sample_feedback.json` → full coverage
  (`sum(frequency) ≈ relevant_count`), real counts, sampled evidence.

## Resolved decisions

- Default model `openai/gpt-4o` at `temperature=0` (Connector's concern; see spec 02). The
  relevance judgment is model-sensitive — `gpt-4o` scores P=0.91/R=1.00 on the labelled eval vs
  `gpt-4o-mini`'s P=0.77/R=0.48; `gpt-4o-mini` remains a cheaper option. Eval harness:
  `scripts/eval_relevance.py`.
- Two LLM layers (relevance gate + index classifier); the model never regenerates item text.
- `frequency` = real count of assigned members; `evidence` = a ≤`SAMPLE_QUOTES` sample. Count and
  shown quotes are decoupled.
- Auditability / coverage repair (persisting the indexed corpus + assignment map; a repair pass
  for unassigned stragglers) is a follow-on — see spec 04.
