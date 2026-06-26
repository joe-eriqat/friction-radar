# Module Spec 03 — Ingestion (collection)

**Status:** accepted (2026-06-25) · **Build order:** 3rd (Demo) / 6th (Upload) / 7th (Scrape)

## Purpose

Any source → normalized `list[FeedbackItem]`. One module, three adapters, a common output.
Ingestion **collects and normalizes**. It runs **no LLM except** the UploadAdapter's
messy-text segmentation fallback (a focused, fidelity-verified call — see below); DemoAdapter,
CSV/JSON, and clean-text parsing stay deterministic. All interpretation (classify / cluster /
judge) still happens downstream in AI Processing.

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

## UploadAdapter (build 6th) — handles messy, inconsistent input

Real exports vary wildly: CSV with arbitrary columns, JSON, or free-text dumps with preamble,
separator bars, numbered/bulleted lists, blank-line paragraphs, multi-line wrapped comments,
interleaved metadata, and **mixed styles within one paste**. Two tiers.

**Structured → deterministic (no LLM):**
- **CSV** — sniff delimiter + header (`csv.Sniffer`); auto-pick the text column (name match
  `comment|text|review|feedback|body`, else the longest-average-length column); one row → one
  item; map `source`/`url`/`date` columns when present.
- **JSON** — array of strings → items; array of objects → the text field.

**Free-text → clean vs messy (the runtime "do we need the LLM?" gate):**
1. **`_looks_messy(text)`** → use the LLM if **any** of:
   - a non-blank line is a separator/decoration bar (`^\s*[-=*_#~]{3,}\s*$`, e.g. `====`, `----`);
   - more than ~30% of non-blank lines are fragment-like (very short, punctuation-only, or
     `key: value` metadata such as author/date/platform);
   - there are ≥2 blank-line paragraphs **and** line-count ≫ paragraph-count (i.e. a line-split
     would shred multi-line comments).
   Otherwise **clean** → deterministic split (paragraphs if present, else one-per-line), **no
   LLM call**. (Thresholds are starting values, tunable against the segmentation eval.)
2. **Messy → LLM segmentation:** the model returns the feedback comments **verbatim**
   (schema `{comments: list[str]}`), excluding preamble / separators / metadata and keeping
   multi-line comments whole. The prompt forbids paraphrase, merge, or invention.
3. **Fidelity guardrail (deterministic):** each returned comment must be a **normalized
   substring of the source**; anything that isn't is dropped (catches paraphrase / wrong merge /
   hallucination). Substring — not equality — so the same check later supports pulling a
   relevant **sub-span** of a long comment.

Then the module-wide normalize (strip / dedupe / drop empty). `source="upload"` (file) or
`"pasted"` (paste box).

`UploadAdapter.load(raw, *, fmt="auto", connector=None)` — injectable connector for the
fallback only; tests use a fake, and the clean / CSV / JSON paths never touch it.

- **AC:**
  1. Format auto-detected (JSON / CSV / free-text); unsupported or empty → `ValueError`.
  2. CSV: delimiter sniffed; text column correctly picked across differing schemas; one item/row;
     metadata mapped where present.
  3. Clean free-text (one-per-line or clean paragraphs) parses **without** any LLM call.
  4. Messy free-text routes to LLM segmentation.
  5. **Fidelity:** every item is verbatim-present in the source; paraphrased/invented dropped;
     no item is a separator bar, preamble, or pure-metadata line.
  6. Count sanity: a known messy dump → ~true count (the StayNest paste → ~72, not 165).
  7. Normalize applies; `source` stamped; zero usable items → `ValueError`.
- **Test:** CSV/JSON fixtures (varied schemas); clean text → asserts the connector is **not**
  called; messy-text fixture (preamble + `====` + multi-line) → fake connector segments + the
  guardrail drops a planted paraphrase. **Segmentation eval** (key-gated, real LLM): the messy
  StayNest dump → recovers ~72 verbatim comments.
- **SPA wiring (orchestration):** the paste box POSTs the **raw** text (and file uploads send
  the raw file) to a `/api/ingest` endpoint → `UploadAdapter` → `AnalyzeRequest`; the SPA shows
  the parsed comment count before Analyze. Replaces the current client-side `split("\n")`.

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
