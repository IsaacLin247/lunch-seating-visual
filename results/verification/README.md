# Independent verification of the publication evidence

The final combined study has **34 attempts: 32 successful traces and two recorded
process interruptions**, covering **517 rotations**. The authoritative manifest
is `../verified_experiments.json`, SHA-256
`18fa11f92db61a4396d3a6b60f3bc6384e175b60cee7fad38500ff60cc3f489b`.

The final reports are:

- `combined_charts.json`: all 32 full traces; zero discrepancies in unique
  placement, capacities, eligibility, anchors, all recorded stage costs,
  per-rotation/aggregate statistics, coalition outcomes, fairness summaries,
  input identities, and trace hashes. This covers 517 proposed charts, 517
  random charts, and 2,068 recorded stage endpoints.
- `combined_privacy.json`: independent binary set-cover/exclusion checks of
  **19,296 forced directed entries across the 32 traces**, with zero metric
  discrepancies and zero unresolved proofs. Reused checks require the same
  trace hash, checker implementation, Python version, and OR-Tools version.
- `hardening_compatibility.json`: the strengthened returned-configuration guard
  accepts every retained full trace.
- `cp_priority_compatibility.json`: the later feasibility-priority guard would
  change no recorded experimental decision. The seven invalid annealing
  endpoints had five initial UNKNOWN CP outcomes and two feasible CP candidates
  already accepted at lower cost.
- `figure_integrity.json`: the six final vector figures and their evidence
  sidecars refer to the same final manifest and retained source.

The earlier `core_*` and `sensitivity_*` reports are per-batch checks or explicitly
sized intermediate snapshots; their recorded trace counts define their scope.
The two `combined_*` reports supersede them for the final paper.

The experiments used effective source
`4282fb6588006917a0fdd94339113c4799d1f26cd5bb37f0e67a3282bc764ed8`,
retained byte for byte under `../source_snapshots/`. Later integrity and CP
acceptance hardening is deliberately distinguished from that archived source.
All public-cap-eight results were calculated without public exact-length inputs;
the repaired exact-length peer-universe boundary therefore does not alter them.

To recheck the saved evidence from the repository root without changing the
experiment inventory:

```sh
python results/verification/verify_traces.py results/verified_experiments.json --out results/verification/combined_charts.json
.venv/bin/python results/verification/verify_privacy.py results/verified_experiments.json --out results/verification/combined_privacy.json
```

Add `--no-reuse` to the privacy check to recompute every exclusion proof.
