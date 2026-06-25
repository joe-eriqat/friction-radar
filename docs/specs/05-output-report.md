# Module Spec 05 — Output / Report (the moat)

**Status:** accepted (2026-06-25) · **Build order:** 4th

## Purpose

`OnboardingReport` → a deterministic view model + share-ready exports. This is where the
product value lives: a structured, repeatable, screenshot-ready artifact. Pure functions,
no I/O, no model.

## Public interface

```python
def view_model(report: OnboardingReport) -> ReportView      # sorted, for the SPA
def to_markdown(report: OnboardingReport) -> str            # share / screenshot
def to_json(report: OnboardingReport) -> str                # canonical, re-importable
```

## In / Out

- **In:** an `OnboardingReport` (+ `id`, `created_at` when persisted).
- **Out:** a sorted view model; Markdown; canonical JSON. (HTML printable view optional later.)

## Acceptance criteria

1. **Prioritization:** themes sorted by severity (`high > medium > low`) then `frequency`
   desc, **stable**. Same report in → same order out, every time.
2. Markdown contains product, summary, and every theme (type, severity, stage, frequency,
   evidence quotes, recommendation); valid Markdown; **no data loss** vs the report.
3. JSON is the canonical serialization and **re-imports into an equal `OnboardingReport`**.
4. Each rendered evidence quote shows its `source`/`url` when present (traceability surfaced,
   not just stored).
5. Empty `themes` → explicit "no themes found" state, never a crash.

## Testing

Golden-file tests against a fixture report:

- assert sorted order (severity then frequency).
- assert Markdown matches a snapshot.
- assert `to_json` re-parses into an `OnboardingReport` equal to the input.
- assert the empty-themes path renders the empty state.
