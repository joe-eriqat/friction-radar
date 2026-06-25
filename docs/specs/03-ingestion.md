# Module Spec 03 — Ingestion (collection)

**Status:** accepted (2026-06-25) · **Build order:** 3rd (Demo) / 6th (Upload) / 7th (Scrape)

## Purpose

Any source → normalized `list[FeedbackItem]`. One module, three adapters, a common output.
Ingestion **collects and normalizes only** — no LLM runs here. All interpretation
(classify / cluster / judge) happens once, downstream, in AI Processing.

```python
class Ingestor(Protocol):
    def load(self, **params) -> list[FeedbackItem]: ...
```

## Module-wide acceptance criteria

1. Every returned item has non-empty `text` (stripped); blank items dropped.
2. Exact-duplicate `text` deduped (keep first occurrence + its metadata).
3. `source` set correctly per adapter.
4. A non-empty input that yields zero usable items → `ValueError("no usable feedback found")`,
   never a silent empty list.

## DemoAdapter (build 1st)

- **In:** dataset id (default = bundled). **Out:** items from `data/sample_feedback.json`,
  `source="demo"`.
- **AC:** unknown id → `ValueError`; all items valid.
- **Test:** default load → N items, all valid, `source == "demo"`.

## UploadAdapter (build later)

- **In:** raw text/bytes + format (`csv`|`text`, auto-detected) + optional CSV column map
  (text/source/url/date). **Out:** `list[FeedbackItem]`.
- **AC:** CSV → one item per row, blanks dropped, `source` from column or `"upload"`; pasted
  text → split on blank-line paragraphs; malformed CSV → `ValueError` with row context
  (no crash); over size cap (1000 items) → reject with a clear error.
- **Test:** CSV fixture → expected items; text blob → expected count; malformed → `ValueError`;
  empty → `ValueError`.

## ScrapeAdapter (build last — ambitious, fragile)

Mechanism is **keyword search**, not LLM inference: query official APIs / fixed sites with the
product name + onboarding terms, fetch matches, normalize. (An LLM-driven discovery agent is a
possible later variant; keyword-first by default.)

- **In:** source type + query/url(s) + `max_items` / `timeout`. **Out:** items with
  `source`/`url`/`date` populated.
- **AC:** respects `max_items`, a per-domain rate cap, and `timeout`; one failed source →
  partial results + warning (not total failure); zero items overall → `ValueError`; prefers
  official API / search+fetch over raw HTML.
- **Test:** recorded HTTP fixtures in CI; live test opt-in / gated.

Adapters ship incrementally — each is additive with zero downstream change.
