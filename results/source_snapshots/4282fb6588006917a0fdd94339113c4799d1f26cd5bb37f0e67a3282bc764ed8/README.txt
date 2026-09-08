Exact effective source used for the publication evidence.

The sim/ files and requirements.txt are copied byte for byte and checked
against source_identity.json. Generated outputs are outside the source hash.
The containing Git commit alone does not identify these uncommitted files.

To replay from the repository root with the pinned environment, run:

.venv/bin/python results/source_snapshots/4282fb6588006917a0fdd94339113c4799d1f26cd5bb37f0e67a3282bc764ed8/sim/experiments.py --seed-values 7 --scenarios honest --skip-budgets --skip-communities --out /tmp/seating-source-replay.json

The output path is deliberately explicit. Timing and generation timestamps
will vary; compare the seating charts and recomputed statistics.
