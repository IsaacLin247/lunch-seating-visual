Exact effective source used for the revised study (September 2026).

The sim/ files and requirements.txt are copied byte for byte and checked
against source_identity.json. Generated outputs are outside the source hash.
The containing Git commit alone does not identify these files.

To replay from the repository root with the pinned environment, run:

.venv/bin/python results/source_snapshots/e1a4d21af6c3e2c42dc8ad8d448005a79abe393a0927d466e591b24f7f9561bb/sim/experiments.py --seed-values 7 --scenarios honest --skip-budgets --skip-communities --out /tmp/seating-source-replay.json

Timing and generation timestamps will vary; compare the seating charts and
recomputed statistics.
