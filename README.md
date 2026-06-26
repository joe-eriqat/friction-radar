# Friction Radar

**Turn messy public customer feedback into a structured, quantified onboarding-intelligence report.**

**▶ [Live demo](https://joe-eriqat.github.io/friction-radar/)** — no sign-up, no API key. Pick a
sample company (StayNest, AuraQuill, LumenLedger), hit **Run demo**, and read a real, pre-captured
analysis. It's a static page replaying genuine pipeline output; to run it on your own feedback,
[clone and bring your own key](#quickstart).

Friction Radar reads public feedback about a product — reviews, Reddit threads, app-store posts,
support exports — and surfaces *where users succeed or struggle during onboarding and early
activation*. It clusters the feedback into themes (success / failure / churn), counts how often
each one shows up, backs every theme with real quotes, and recommends concrete fixes — then lets
you export the whole thing as a share-ready report.

It is deliberately **not a GPT wrapper.** The value is the *artifact* — a repeatable, comparable,
screenshot-ready report — and the deterministic machinery wrapped around the model that makes it
trustworthy:

- a **relevance gate** that drops off-topic noise before clustering,
- **index-based classification** (the model assigns each comment to a theme *by number*, never
  by regenerating text) so counts are real, coverage is complete, and quotes can't be
  hallucinated,
- a **verbatim-verified segmenter** that parses a messy paste/export into clean individual
  comments without ever altering them.

## How it works

```
raw paste / file / CSV / JSON
  → Ingestion        parse into clean comments (deterministic for CSV/JSON;
                     LLM segmentation, verbatim-verified, for messy text)
  → Relevance gate   drop comments that aren't about this product
  → Classifier       group comments into themes BY INDEX (no regenerated text)
  → Assemble         deterministic: real counts, sampled evidence + provenance, coverage
  → Report           prioritized view + Markdown / JSON export, persisted to SQLite
```

The model makes only two narrow judgments — *is this relevant?* and *which theme?* — and
references comments by index. Everything else (counting, sampling, ordering, exporting) is
deterministic code.

## Measured quality

Scored against hand-labelled comment sets across three unrelated domains (a health app, a rental
marketplace, a finance app):

- **Relevance** (off-topic detection): precision 0.91–0.96, recall 1.00.
- **Coverage** (relevant comments assigned to a theme): 98–100%.
- **Segmentation** (recovering verbatim comments from a messy dump): 0.99 recall.

The eval harnesses live in `scripts/eval_relevance.py` and `scripts/eval_segmentation.py`.

## Quickstart

```bash
git clone https://github.com/joe-eriqat/friction-radar.git
cd friction-radar
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cp .env.example .env          # then add your OpenAI key:  OPENAI_API_KEY=sk-...
./run.sh                      # serves http://127.0.0.1:8080
```

Open the page → pick a **sample** (or paste/upload your own feedback) → **Analyze onboarding**.

Tick **⚡ Demo mode** to replay a captured run for the selected sample instantly, with no model
call — handy with no key, or to show the output without spending tokens.

### The static demo (no backend)

The live demo above is this same UI built to a backend-free static site:

```bash
./venv/bin/python scripts/bake_demos.py     # capture real runs into data/demos/ (needs a key, run once)
./venv/bin/python scripts/build_static.py   # assemble ./site/ from the committed assets (no key)
python3 -m http.server -d site 8000         # preview
```

`bake_demos.py` is the only step that spends tokens; the committed `data/demos/` output then drives
the free demo. Pushing to `main` republishes the site via GitHub Pages (`.github/workflows/pages.yml`).

## Configuration (`.env`)

| Var | Meaning |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI key. |
| `FRICTION_RADAR_MODEL` | LiteLLM model string. Default `openai/gpt-5.4` (strong); `openai/gpt-4o-mini` is much cheaper/weaker. |
| `FRICTION_RADAR_LLM_BASE_URL` | Optional OpenAI-compatible endpoint (any provider LiteLLM supports). |
| `FRICTION_RADAR_TEMPERATURE` | Default `0` (stable categorization). `none` to omit for models that reject it. |
| `FRICTION_RADAR_DB` | SQLite path (default `friction_radar.db`). |

Provider is fully config-driven via [LiteLLM](https://github.com/BerriAI/litellm) — point it at
OpenAI, an OpenAI-compatible gateway, or another provider without code changes.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/samples` | List bundled demo datasets |
| `GET` | `/api/sample?name=…` | Load one demo dataset |
| `POST` | `/api/ingest` | Raw paste/file (CSV/JSON/messy text) → parsed feedback |
| `POST` | `/api/analyze` | Feedback → stored report |
| `GET` | `/api/reports` · `/api/reports/{id}` · `/api/reports/{id}/view` | List / fetch / prioritized view |
| `GET` | `/api/reports/{id}/export?format=md\|json` | Export a report |

## Output

Each report clusters feedback into themes of three kinds:

- **Success points** — clarity, delight, fast activation, a "magic moment."
- **Failure points** — confusion, friction, unmet expectations, unclear pricing.
- **Churn / drop-off** — language showing the user gave up, switched away, or uninstalled.

Every theme carries a severity, a real mention count, representative quotes (with their source),
and a concrete recommendation. Reports are persisted so past runs can be listed, re-opened, and
exported.

## Stack

Python 3.13 · FastAPI · [LiteLLM](https://github.com/BerriAI/litellm) (provider-agnostic) ·
SQLite · vanilla-JS single-page UI. No Node, no build step.

## Limitations

- Sentiment/themes are directional — validate against real user interviews and analytics.
- Theme prevalence reflects the input you give it; biased input → biased report.
- A research aid for onboarding, not a replacement for product instrumentation.

## Roadmap

- A live source or two (e.g. a Reddit thread via its public JSON), reusing the existing segmenter.
- Competitor comparison; run-to-run diffing; exports to Linear / Notion / Jira.

## License

MIT — see [LICENSE](LICENSE).
