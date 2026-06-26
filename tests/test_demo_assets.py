"""Demo-mode assets + build (spec 08).

Validates the *committed* demo artifacts (datasets, canned reports, manifest) that power
LLM-free / static mode, and unit-tests the deterministic parts of the bake/build scripts.
No network: these never call a model.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.output import ReportView

REPO = Path(__file__).resolve().parent.parent
DEMOS = REPO / "data" / "demos"
CANNED = DEMOS / "canned"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- committed assets ----------------------------------------------------------------

def _manifest() -> list[dict]:
    return json.loads((DEMOS / "index.json").read_text())


def test_manifest_exists_and_nonempty():
    assert _manifest(), "data/demos/index.json should list at least one demo"


@pytest.mark.parametrize("entry", _manifest())
def test_manifest_entry_has_dataset_and_canned(entry):
    did = entry["id"]
    ds = DEMOS / f"{did}.json"
    cn = CANNED / f"{did}.json"
    assert ds.exists(), f"missing dataset for {did}"
    assert cn.exists(), f"missing canned report for {did}"

    data = json.loads(ds.read_text())
    assert data.get("product"), f"{did}: dataset needs a product"
    fb = data.get("feedback") or []
    assert fb and all(item.get("text") for item in fb), f"{did}: feedback items need text"
    assert entry["count"] == len(fb), f"{did}: manifest count out of sync with dataset"


@pytest.mark.parametrize("entry", _manifest())
def test_canned_report_is_valid_reportview(entry):
    view = ReportView(**json.loads((CANNED / f"{entry['id']}.json").read_text()))
    assert view.product and view.summary
    assert view.theme_count == len(view.themes)
    # canned evidence quotes must trace to dataset comments (no invented quotes)
    corpus = {
        i["text"] for i in json.loads((DEMOS / f"{entry['id']}.json").read_text())["feedback"]
    }
    norm = {" ".join(t.split()).casefold() for t in corpus}
    for theme in view.themes:
        for ev in theme.evidence:
            q = " ".join(ev.quote.split()).casefold()
            assert any(q in c for c in norm), f"{entry['id']}: quote not in dataset: {ev.quote!r}"


# ---- bake script: deterministic parsing (no LLM) -------------------------------------

def test_bake_split_and_clean_parse():
    bake = _load_script("bake_demos")
    src = (
        "--COMPANY DESCRIPTION\nAcme makes widgets.\n\n"
        "--COMMENT DATA\n"
        "===== DOC-01: somewhere =====\n"
        "[X-1] platform=reddit | author=u/a\nSetup was slow.\n\n"
        "[X-2] platform=twitter | author=@b\nLoved it, multiple\nlines here.\n"
    )
    p = REPO / "tests" / "_tmp_demo.txt"
    p.write_text(src)
    try:
        product, block = bake._split_source(p)
        assert product == "Acme makes widgets."
        items = bake._parse_clean(block)
        assert [(i.source, i.text) for i in items] == [
            ("reddit", "Setup was slow."),
            ("twitter", "Loved it, multiple lines here."),
        ]
    finally:
        p.unlink()


# ---- static build: flag + relative paths --------------------------------------------

def test_static_build_injects_flag(tmp_path):
    build = _load_script("build_static")
    html = (REPO / "static" / "index.html").read_text()
    out = html.replace("</head>", build.STATIC_FLAG + "</head>", 1)
    assert "window.FRICTION_RADAR_STATIC = true" in out
    # demo assets must be fetched via a relative base (works under a Pages subpath),
    # never an absolute "/demos" path.
    assert 'const DEMO_BASE = "demos"' in html
    assert 'fetch("/demos' not in html
