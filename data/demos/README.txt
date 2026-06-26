# Demo assets that power LLM-free / static demo mode (spec 08). Generated, but committed.
#
#   <id>.json          dataset: {name, product, feedback:[{text, source}]}
#   canned/<id>.json   a real captured ReportView for that dataset (what demo mode replays)
#   index.json         manifest the picker / static site reads (it can't glob a directory)
#
# Regenerate from docs/*Demo.txt with a funded key:  ./venv/bin/python scripts/bake_demos.py
# (clean dumps are parsed deterministically; messy dumps go through the live segmenter.)
# Build the backend-free static site from these:      ./venv/bin/python scripts/build_static.py
