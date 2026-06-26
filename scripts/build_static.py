#!/usr/bin/env python3
"""Assemble a backend-free static demo site (spec 08) into ./site/.

The output is self-contained and uses only relative paths, so it works from `file://`, any
static host, or GitHub Pages under a project subpath. It runs purely in LLM-free demo mode:
the picker, datasets, and canned reports are the committed JSON under data/demos/.

    ./venv/bin/python scripts/bake_demos.py     # capture real runs first (needs a key)
    ./venv/bin/python scripts/build_static.py   # then build the static site (no key needed)

Open site/index.html, or serve it:  python3 -m http.server -d site 8000
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_INDEX = REPO / "static" / "index.html"
DEMOS = REPO / "data" / "demos"
SITE = REPO / "site"

# Sets the flag the SPA checks at load to force demo mode and hide live-only controls.
STATIC_FLAG = "<script>window.FRICTION_RADAR_STATIC = true;</script>\n"


def main() -> None:
    if not (DEMOS / "index.json").exists():
        sys.exit("data/demos/index.json missing — run scripts/bake_demos.py first.")

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    # index.html with the static flag injected so it runs before the inline app script.
    html = SRC_INDEX.read_text(encoding="utf-8")
    if "</head>" not in html:
        sys.exit("static/index.html has no </head> to inject the static flag into.")
    html = html.replace("</head>", STATIC_FLAG + "</head>", 1)
    (SITE / "index.html").write_text(html, encoding="utf-8")

    # demo assets at the same relative path the dev backend mounts (/demos).
    shutil.copytree(
        DEMOS, SITE / "demos",
        ignore=shutil.ignore_patterns("README.txt"),
    )

    files = sum(1 for _ in (SITE / "demos").rglob("*.json"))
    print(f"built {SITE.relative_to(REPO)}/  (index.html + {files} demo json files)")
    print(f"preview:  python3 -m http.server -d {SITE.relative_to(REPO)} 8000")


if __name__ == "__main__":
    main()
