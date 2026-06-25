# Friction Radar — local development

A lightweight, demo-first implementation of the vision in [`README.md`](README.md).

**Stack:** Python 3.13 · FastAPI · Anthropic Claude (structured outputs) · SQLite · vanilla-JS single-page UI.
No Node, no build step, no live scrapers — runs on bundled / pasted feedback (demo mode).

## Layout

```
app/
  schemas.py    Pydantic models — also the structured-output contract for Claude
  analyzer.py   The AI core: one Claude call → validated OnboardingReport
  store.py      SQLite persistence (reports table)
  main.py       FastAPI app: serves the UI + /api/* endpoints
data/
  sample_feedback.json   Demo dataset (no scraping required)
static/
  index.html    Single-page UI (paste feedback → report + prioritized table)
scripts/
  smoke_test.py End-to-end check against the sample dataset
run.sh          Launch helper
```

## Setup

```bash
cd /opt/friction-radar
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Configuration is via environment / `.env` (see `.env.example`):

- `ANTHROPIC_API_KEY` — already exported globally on this host; only set it to override.
- `FRICTION_RADAR_MODEL` — defaults to `claude-opus-4-8`; set `claude-haiku-4-5` for cheaper/faster runs.
- `FRICTION_RADAR_DB` — SQLite path (default `friction_radar.db` in the repo root).

## Run

```bash
./run.sh                 # http://127.0.0.1:8080
HOST=0.0.0.0 PORT=9000 ./run.sh
```

Open the page → **Load sample dataset** → **Analyze onboarding**.

## API

| Method | Path                  | Purpose                                   |
|--------|-----------------------|-------------------------------------------|
| GET    | `/`                   | Single-page UI                            |
| GET    | `/api/sample`         | Bundled demo dataset                      |
| POST   | `/api/analyze`        | `{product, feedback:[...]}` → stored report |
| GET    | `/api/reports`        | List past reports                         |
| GET    | `/api/reports/{id}`   | Fetch one report                          |

## Smoke test

```bash
./venv/bin/python scripts/smoke_test.py            # uses the default model
FRICTION_RADAR_MODEL=claude-haiku-4-5 ./venv/bin/python scripts/smoke_test.py
```

> **Note:** Live analysis requires a funded Anthropic account. If you see
> `Your credit balance is too low`, the API key authenticates but has no credits —
> add credits (or point `ANTHROPIC_API_KEY` at a funded key). Everything else
> (UI, sample loading, persistence) runs without API access.

## How it works

`analyzer.py` sends the product + feedback list to Claude in a single
`client.messages.parse(..., output_format=OnboardingReport)` call. Because the Pydantic
model is the output schema, the response is validated into typed objects (themes with
type / severity / onboarding-stage / evidence quotes / recommendation) before it reaches
the API layer — no hand-rolled JSON parsing. Reports are persisted to SQLite so past runs
can be listed and re-opened without re-calling the model.

## Not yet built (future work, per README)

Live connectors (Reddit, app stores, G2), competitor comparison, exports to Linear/Notion/Jira.
