# Friction Radar — local development

A lightweight, demo-first implementation of the vision in [`README.md`](README.md).

**Stack:** Python 3.13 · FastAPI · [LiteLLM](https://github.com/BerriAI/litellm) (provider-agnostic
structured outputs) · SQLite · vanilla-JS single-page UI.
No Node, no build step. Runs on bundled demo datasets or pasted / uploaded feedback.

## Layout

```
app/
  schemas.py     Pydantic models — FeedbackItem, Theme, Evidence, OnboardingReport, AnalyzeRequest
  connector.py   LiteLLMConnector — one provider-agnostic structured-output seam (strict or JSON-mode)
  ingestion.py   Demo datasets + UploadAdapter (CSV/JSON deterministic; messy text → verbatim segmenter)
  processing.py  The AI core: relevance gate → index-based classifier → deterministic assemble
  output.py      Prioritized view model + Markdown / canonical-JSON export
  store.py       SQLite persistence (reports table)
  main.py        FastAPI app: serves the UI + /api/* endpoints
data/
  sample_feedback.json   Default bundled demo dataset
  demos/*.json           Additional demo datasets (each {name?, product, feedback:[...]})
static/
  index.html     Single-page UI (pick a demo / paste / upload → report + prioritized table)
scripts/
  smoke_connector.py     Live connector check against a real provider
  eval_relevance.py      Score the relevance gate against a labelled key
  eval_segmentation.py   Score messy-dump segmentation recall against a labelled key
run.sh           Launch helper
```

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env     # add your key
```

Configuration is via environment / `.env` (see `.env.example`):

- `OPENAI_API_KEY` — your provider key (required for live analysis).
- `FRICTION_RADAR_MODEL` — LiteLLM model string. Default `openai/gpt-5.4`; `openai/gpt-4o-mini`
  is cheaper/weaker (relevance is judgment-heavy — the small model misses more).
- `FRICTION_RADAR_LLM_BASE_URL` — optional OpenAI-compatible endpoint.
- `FRICTION_RADAR_TEMPERATURE` — default `0` (stable categorization); `none` omits the param.
- `FRICTION_RADAR_DB` — SQLite path (default `friction_radar.db` in the repo root).

## Run

```bash
./run.sh                       # http://127.0.0.1:8080
HOST=0.0.0.0 PORT=9000 ./run.sh
```

Open the page → pick a sample (or paste / upload feedback) → **Analyze onboarding**.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/`                          | Single-page UI |
| GET  | `/api/samples`               | List bundled demo datasets |
| GET  | `/api/sample?name=…`         | Load one demo dataset (omit `name` for the default) |
| POST | `/api/ingest`                | `{product, raw, source}` → parsed `{product, feedback:[...]}` |
| POST | `/api/analyze`               | `{product, feedback:[...]}` → stored report |
| GET  | `/api/reports`               | List past reports |
| GET  | `/api/reports/{id}`          | Fetch one report |
| GET  | `/api/reports/{id}/view`     | Prioritized presentation view |
| GET  | `/api/reports/{id}/export?format=md\|json` | Export a report |

## Tests

Offline (no network — the connector seam is monkeypatched):

```bash
./venv/bin/python -m pytest -q
```

Live checks (require a funded key):

```bash
./venv/bin/python scripts/smoke_connector.py
./venv/bin/python scripts/eval_relevance.py [key.csv] ["product description"]
./venv/bin/python scripts/eval_segmentation.py [key.csv]
```

> **Note:** Live analysis requires a funded provider account. If the key authenticates but has no
> credit, calls fail at the provider — everything else (UI, demo loading, persistence) runs without
> API access.

## How it works

The pipeline keeps the model's job narrow and makes everything else deterministic:

1. **Ingestion** (`ingestion.py`) — CSV / JSON parse deterministically (no LLM). Messy free text is
   routed by `_looks_messy` (separator bars, metadata ratio, wrapped-line detection): clean input is
   split deterministically; messy input goes to an LLM segmenter that must return **verbatim**
   comments, each verified as a normalized substring of the source (no paraphrase or invention).
2. **Relevance gate** (`processing.py`) — a general, product-type-agnostic Layer-1 call drops
   clearly off-topic comments by index. All-off-topic → `ValueError`.
3. **Index-based classifier** — assigns each surviving comment to a theme **by its index number**;
   the model never regenerates quote text.
4. **Assemble** — deterministic: `frequency` is the real member count, `evidence` is a small sample
   with provenance, single-assignment is enforced, out-of-range/duplicate indices are dropped, and
   `total_feedback` / `relevant_count` make coverage observable.

Because the model only judges *relevant?* and *which theme?* and references comments by index, counts
are real, coverage is measurable, and quotes can't be hallucinated. Reports are persisted to SQLite
so past runs can be listed, re-opened, and exported.

The full module specs (with acceptance criteria) live in [`docs/specs/`](docs/specs/).

## Not yet built (future work, per README)

A live scrape adapter (e.g. a Reddit thread via its public JSON, reusing the segmenter), competitor
comparison, run-to-run diffing, and exports to Linear / Notion / Jira.
