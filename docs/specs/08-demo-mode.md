# Module Spec 08 — Demo Mode + Static Deploy

**Status:** accepted (2026-06-26) · **Build order:** after 07 (frontend) · extends ingestion + frontend

## Purpose

Let anyone see Friction Radar work in seconds — **without a hosted server and without us
handing out tokens.** Two outcomes from one codebase:

1. **Demo dropdown** on the main page loads a bundled sample (company description + its feedback)
   and runs it.
2. **LLM-free mode** replays a *real* prior run's output instead of calling any model — so the
   product can be demonstrated end-to-end with no API key and no cost.

Because LLM-free mode needs no secrets and no compute, the same SPA can be published as a **static
GitHub Pages site**: a single public link, free for public repos, nothing for us to run. The live
backend path (bring-your-own-key, `./run.sh`) is unchanged and remains the "run it for real" story.

## In / Out

- **In:** a selected demo id; a mode flag (live vs. LLM-free); for the live path, the existing
  product + feedback inputs.
- **Out:** a rendered report. In live mode via `/api/*`; in LLM-free mode from committed canned
  JSON, with no network calls to any model.

## The three pieces

### 1. Demo datasets — `data/demos/*.json`  *(exists)*

`{name?, product, feedback: [str | {text, source, url?, date?}]}`. Already consumed by the picker
via `GET /api/samples` / `GET /api/sample?name=`. `staynest.json` is baked. The two intentionally
messy authored dumps (AuraQuill, LumenLedger) are **not** parsed deterministically — their datasets
are produced by the bake step below (the live segmenter run is part of capturing them).

### 2. Canned reports — `data/demos/canned/<id>.json`  *(new)*

One file per demo id, holding **exactly the `ReportView` shape** the SPA's `render()` already
consumes (so replay and live render identically):

```json
{
  "product": "...",
  "summary": "...",
  "total_feedback": 72,
  "relevant_count": 58,
  "themes": [
    { "type": "...", "title": "...", "frequency": 12, "impact": "...",
      "evidence": [ { "quote": "...", "source": "reddit", "url": null } ] }
  ]
}
```

These are authentic: generated once by running the **real pipeline** (ingest → analyze →
`output.view_model`) on the author's key, then committed. This is the only place a token is ever
spent, and only by us, once per dataset refresh.

### 3. Mode switch + data-source seam  *(new)*

The frontend gets one small indirection: a **data-source layer** with two backends behind the same
calls the UI already makes (`listDemos`, `loadDemo(id)`, `run(...) → view`):

- **live backend** — today's `/api/*` calls (ingest + analyze + view). Unchanged.
- **static backend** — `fetch` of committed JSON only, no POST, no server:
  - picker list ← `data/demos/index.json` (a manifest the bake/build writes; a static host can't
    glob a directory)
  - dataset ← `data/demos/<id>.json`
  - report ← `data/demos/canned/<id>.json`

**Mode selection:**

- A UI toggle **"Demo mode — no API key, instant"**. When on, Run replays the canned view for the
  selected demo instead of calling the model.
- Static builds set `window.FRICTION_RADAR_STATIC = true` (injected by the build, see §4). In a
  static build the toggle is **forced on and hidden** — there is no backend to call. Run locally
  with the backend up, the toggle is user-controllable, so the same page demos both replay *and*
  the live pipeline.
- LLM-free mode requires a canned file for the chosen demo; if missing, the UI says so rather than
  silently failing. Free-text / upload input is a live-only path (it's disabled in static mode).

**Exports in LLM-free mode:** export links currently hit `/api/reports/{id}/export`. In static
mode, Markdown/JSON are generated **client-side from the canned view** (same fields), so downloads
work with no backend.

## 4. Static build + GitHub Pages

- `scripts/build_static.py` assembles a self-contained `site/`: `static/index.html` (with an
  inline `<script>window.FRICTION_RADAR_STATIC = true</script>` injected into `<head>` so it runs
  before the app script) and the whole `data/demos/` tree copied to `site/demos/` (datasets, canned
  reports, manifest). All asset paths are **relative** (`demos/…`, no leading `/`) so it works under
  a project Pages subpath. In dev, FastAPI mounts the same tree at `/demos`, so the SPA's demo code
  path is identical in both.
- A GitHub Actions workflow builds `site/` and deploys to Pages on push to `main`. No build
  artifacts are committed to the repo.
- README gets a top-of-file **▶ Live demo** link to the Pages URL; the "run it for real" quickstart
  stays as the bring-your-own-key path.

## Bake script — `scripts/bake_demos.py`

One command, run by the author with a funded key, to (re)generate committed demo assets:

1. For each authored source (clean `data/demos/*.json`, or messy `docs/*Demo.txt` via the live
   `UploadAdapter` segmenter), produce the dataset JSON under `data/demos/<id>.json`.
2. Run the real pipeline on it and write `data/demos/canned/<id>.json` (the `ReportView`).
3. Write/refresh `data/demos/index.json`.

Output is deterministic to commit (stable key order); re-running refreshes the captured reports.
`scripts/build_demos.py` (the deterministic StayNest converter already written) folds into step 1.

## Acceptance criteria

1. **Picker + run (live):** select a demo → product + feedback populate → Run → real pipeline →
   rendered report. Unchanged from today.
2. **LLM-free replay (backend up):** toggle Demo mode on → select a demo → Run makes **no model
   call** and renders the committed canned view identically to a live render. Verifiable by running
   with no/invalid `OPENAI_API_KEY`.
3. **Static build:** `scripts/build_static.py` produces a `site/` that opens from `file://` or any
   static host, lists demos, runs every demo in LLM-free mode, and exports Markdown/JSON — with the
   network tab showing **zero** model/API calls.
4. **Deploy:** pushing to `main` publishes the Pages site; the README **▶ Live demo** link loads it
   and a first-time visitor reaches a rendered report in a few clicks.
5. **Missing canned file** is surfaced as a clear message, never a silent or broken render.

## Testing

- **Unit:** `bake_demos` writes a valid `ReportView` (schema-validated) + manifest for each demo;
  `build_static` emits relative paths only and the `FRICTION_RADAR_STATIC` flag.
- **Offline:** the static backend renders a canned fixture with the connector seam unused (proves
  no model dependency).
- **Manual checklist (vanilla JS):** toggle behavior, forced-on-in-static, client-side export,
  missing-canned message.
- **Smoke:** `site/index.html` loads and runs one demo end-to-end with the network disabled.

## Out of scope

Live scrape adapters, competitor comparison, run-to-run diffing, external exports (Linear/Notion/
Jira) — tracked under README "future work", unaffected by demo mode.
