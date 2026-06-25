# Spec 00 — Architecture Overview

**Status:** agreed direction (2026-06-25) · **Workflow:** spec-first, one module per chunk.

## Product thesis (why this is not a GPT wrapper)

The value is a **structured, repeatable, shareable onboarding-intelligence artifact** —
not access to a model. The defensible parts are the **Output/report module** and
**persistence** (saved, comparable, screenshot-ready reports), plus normalizing messy bulk
feedback. If the pipeline were just "forward text to GPT with a prompt," upload mode would
be pointless — so the moat lives in structure + artifact, not ingestion.

Implication for ingestion tiers:
- **Demo mode** — presaved sets; the safe default and demo fallback.
- **Upload mode** — reframed as "bring your bulk exports" (app-store CSVs, a Reddit thread
  dump, Zendesk export) that you *can't* cleanly paste into a chat. Cheap, robust.
- **Live scrape** — fixed sites + agent search; the differentiated "wow" but also the
  fragile, ToS/rate-limit/anti-bot-risky tier. Build last; prefer official APIs / a
  search+fetch agent over raw HTML scraping.

## Module map (data-flow order)

| # | Module | Responsibility |
|---|---|---|
| 1 | **Frontend / Input** | Product description, source selection, trigger run, render report |
| 2 | **Ingestion** (adapters) | Any source → normalized `list[FeedbackItem]` |
| 3 | **AI Processing** | `(product, feedback[])` → `OnboardingReport` — see spec 01 |
| 4 | **LLM Connector** | Generic provider wrapper (LiteLLM); sits under #3 — see spec 02 (TODO) |
| 5 | **Storage** | Persist reports (+ feedback sets) → list, re-open, compare |
| 6 | **Output / Report** | `OnboardingReport` → graphical view + exports |
| 0 | **Orchestration/API + Config** | Sequences input→ingest→analyze→store→format; keys/model config |

## Core contracts

```python
# Feedback is metadata-bearing so scraping data (source/url/date) isn't lost.
# Only `text` is required → demo/upload stay trivial.
class FeedbackItem(BaseModel):
    text: str
    source: str | None = None   # e.g. "reddit", "app_store", "g2", "upload", "demo"
    url: str | None = None
    date: str | None = None     # ISO-8601 if known

class AnalyzeRequest(BaseModel):
    product: str
    feedback: list[FeedbackItem]

# OnboardingReport / Theme — unchanged from current app/schemas.py.

class LLMConnector(Protocol):
    def complete_structured(self, *, system: str, user: str,
                            schema: type[BaseModel], max_tokens: int = 4096) -> BaseModel: ...
```

## Ingestion adapter pattern

The three "sources" are **one module + three adapters** behind a common interface, all
converging to `list[FeedbackItem]`. AI Processing never knows the source.

```
Ingestion
 ├─ DemoAdapter    → presaved sets
 ├─ UploadAdapter  → CSV / text / pasted dump → normalized
 └─ ScrapeAdapter  → fixed sites + agent search
```

Ship adapters incrementally; each is additive with zero downstream change.

## Provider strategy

One generic **LLM Connector** (LiteLLM) is the only code that knows about providers.
Provider/model/endpoint = config:
- `FRICTION_RADAR_MODEL` — LiteLLM model string (default suggestion `openai/gpt-4o-mini`)
- `OPENAI_API_KEY` — direct OpenAI
- `FRICTION_RADAR_LLM_BASE_URL` — optional OpenAI-compatible endpoint (e.g. the OpenClaw
  gateway `http://localhost:19000/v1`)

Direct OpenAI and the gateway run the same code path.

## Build order (each = one chunk)

1. **LLM Connector** (spec 02) — LiteLLM wrapper + structured output.
2. **AI Processing** (spec 01) — on top of the connector.
3. **Ingestion: DemoAdapter** — wire demo → ingest → analyze → store end-to-end.
4. **Output / Report** — graphical view + export.
5. **Frontend** — source selection + render.
6. **Ingestion: UploadAdapter** — CSV/text.
7. **Ingestion: ScrapeAdapter** — fixed sites + agent search (ambitious; last).

## Current state (2026-06-25)

- Provider-agnostic scaffolding exists from an earlier pass: `app/schemas.py`,
  `app/store.py` (SQLite), `app/main.py` (FastAPI), `static/index.html` (SPA),
  `data/sample_feedback.json`. These survive.
- `app/analyzer.py` was written against the **Anthropic** SDK and will be **replaced** by
  the LLM-Connector-based AI Processing module. Do not extend the Anthropic version.
- `schemas.py` still has `feedback: list[str]` — to be promoted to `list[FeedbackItem]`
  when AI Processing is implemented.
- Env: no `OPENAI_API_KEY` set; the host's Anthropic key has no credit balance.
