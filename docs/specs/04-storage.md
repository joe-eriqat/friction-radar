# Module Spec 04 — Storage

**Status:** accepted (2026-06-25) · **Build order:** 4th tier (extends existing `app/store.py`)

## Purpose

Persist reports (and their feedback sets) so they can be listed, re-opened, and compared.
Second of the two "moat" modules (with Output). Builds on today's SQLite `store.py`.

## Public interface

```python
def save_report(report: OnboardingReport, feedback: list[FeedbackItem] | None = None) -> StoredReport
def list_reports() -> list[StoredReport]          # newest first
def get_report(report_id: int) -> StoredReport    # raises KeyError if absent
def compare(a: int, b: int) -> ReportDiff
```

## In / Out

- **In:** an `OnboardingReport` (+ optional feedback set); ids; id pairs.
- **Out:** `StoredReport` ( `id`, `created_at`, `product`, `report` ); summaries; a `ReportDiff`.

## Acceptance criteria

1. `save_report` returns a stable unique `id`; `get_report(id)` returns a report **equal** to
   what was saved (full round-trip incl. evidence, metadata, `created_at`).
2. `list_reports()` → newest-first summaries: `id`, `product`, `created_at`, `theme_count`,
   `top_severity`.
3. `get_report(unknown)` → `KeyError` (API maps to 404). *(Today's code returns `None`; this
   spec tightens it to raise — update callers in spec 06.)*
4. `compare(a, b)`: match themes by `title`; return added / removed / changed (severity +
   frequency deltas). Same product assumed; mismatched products flagged in the diff.
5. If a feedback set is passed, the **analyzed corpus** (the relevant items, numbered) and the
   theme→index **assignment map** are stored alongside the report. This makes a run auditable:
   re-trace which comment landed in which theme, recompute coverage, and **score a run against a
   labeled key** (e.g. relevance precision/recall vs an `about_app` answer key — see the eval
   harness). This is the auditability follow-on flagged in spec 01.

## Schema

```
reports(id, created_at, product, payload)                 -- exists
feedback_sets(report_id, items_json, assignments_json)    -- new: analyzed corpus + theme->index map
```

## Testing

- save → get round-trip equality on a fixture report.
- `list_reports` ordering (newest first) + summary fields.
- `get_report(unknown)` → `KeyError`.
- `compare` on two fixtures → expected added/removed/changed diff.
