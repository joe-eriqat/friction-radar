# Module Spec 07 — Frontend / Input

**Status:** accepted (2026-06-25) · **Build order:** 5th · vanilla-JS SPA (`static/index.html`)

## Purpose

Capture product + source, trigger a run, render the report and exports, browse past reports.
No framework / build step.

## In / Out

- **In:** user input — product text, source selection, file/paste for upload.
- **Out:** API calls; a rendered report (prioritized themes + summary + traceable evidence);
  export downloads; report history.

## Acceptance criteria

1. Enter product + select source → trigger → loading state → render prioritized themes
   (using Output's sort order) + summary + evidence with source links.
2. Export buttons download Markdown / JSON; the report list re-opens a saved report.
3. Error states (400 / 502) surfaced to the user — never silent.

## Testing

- Manual acceptance checklist (primary — it's vanilla JS).
- Smoke test: the page loads and "Load sample" populates the input.
- Optional/gated Playwright E2E later.
