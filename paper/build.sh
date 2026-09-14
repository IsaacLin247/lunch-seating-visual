#!/usr/bin/env bash
# Build the verified manuscript and website PDF from retained study evidence.
set -euo pipefail
cd "$(dirname "$0")/.."
seating_python="${SEATING_PYTHON:-.venv/bin/python}"
"$seating_python" paper/assemble_evidence.py --retained-source
"$seating_python" results/verification/verify_traces.py results/revised_experiments.json --out results/verification/revised_charts.json
"$seating_python" results/verification/verify_privacy.py results/revised_experiments.json --out results/verification/revised_privacy.json
# Preserve the incomplete evaluation ledger; generated tables explicitly label
# unfinished attempts and unequal coverage instead of treating this grid as final.
"$seating_python" paper/assemble_evidence.py --retained-source --no-site --partial --inputs results/revised_evaluation_a.json results/revised_evaluation_b.json --out results/revised_evaluation.json
"$seating_python" results/verification/verify_traces.py results/revised_evaluation.json --out results/verification/revised_evaluation_charts.json
"$seating_python" paper/make_tables.py
"$seating_python" paper/make_evaluation.py --manifest results/revised_evaluation.json --retained-source
"$seating_python" paper/make_figures.py --retained-source
latexmk -pdf -interaction=nonstopmode -halt-on-error -cd article/article.tex
latexmk -pdf -interaction=nonstopmode -halt-on-error -cd paper/methodology.tex
cp article/article.pdf docs/article.pdf
