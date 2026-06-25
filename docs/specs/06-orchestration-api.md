# Module Spec 06 — Orchestration / API + Config

**Status:** accepted (2026-06-25) · **Build order:** wires modules as they land

## Purpose

Thin controllers that **sequence** ingest → analyze → store → format; load and validate
config; build the default connector. No business logic in handlers — they only sequence, so
each module stays independently testable.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | SPA |
| GET | `/api/sample` | bundled demo dataset |
| POST | `/api/analyze` | inline feedback **or** a source descriptor → ingest → analyze → store |
| GET | `/api/reports` | list (newest first) |
| GET | `/api/reports/{id}` | one report |
| GET | `/api/reports/{id}/export?format=md\|json` | export |
| GET | `/api/reports/{id}/compare?with={id}` | diff two reports |

## In / Out

- **In:** HTTP requests (JSON bodies / query params).
- **Out:** JSON (stored report + `id` + view model), exports, error envelopes.

## Acceptance criteria

1. `POST /api/analyze` end-to-end: valid request → 200 with a stored report whose `id` is
   retrievable via `GET /api/reports/{id}`.
2. Error mapping: `ValueError` → 400, `KeyError` (not found) → 404, `RuntimeError`
   (connector) → 502.
3. Config validated at startup; missing required config → clear startup error, not a
   request-time 500.
4. Handlers contain only sequencing — all logic lives in the modules they call.

## Testing

FastAPI `TestClient` with a fake connector injected:

- analyze happy path → 200 + retrievable report.
- empty feedback → 400.
- missing report → 404.
- connector failure → 502.
