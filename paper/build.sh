#!/usr/bin/env bash
# Build the verified manuscript and website PDF from retained study evidence.
set -euo pipefail
cd "$(dirname "$0")/.."
seating_python="${SEATING_PYTHON:-.venv/bin/python}"
"$seating_python" paper/assemble_evidence.py --retained-source
"$seating_python" results/verification/verify_traces.py results/verified_experiments.json --out results/verification/combined_charts.json
"$seating_python" results/verification/verify_privacy.py results/verified_experiments.json --out results/verification/combined_privacy.json
"$seating_python" paper/make_tables.py
"$seating_python" paper/make_figures.py --retained-source
latexmk -pdf -interaction=nonstopmode -halt-on-error -cd article/article.tex
latexmk -pdf -interaction=nonstopmode -halt-on-error -cd paper/methodology.tex
cp article/article.pdf docs/article.pdf
