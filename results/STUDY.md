# Fresh verified study, 8 September 2026

The study uses the minimize-extras implementation with targeted-core screening, grade-specific capacity pools, three screening outcomes, actual stage snapshots, and a public-cap privacy observer. Historical `experiments.json` is preserved but excluded from the new tables and figures.

The planned study has32 successful configurations:20 primary population/scenario pairs, four additional reference attacks, four computational-budget settings, two horizon settings, and two community settings. The final manifest is the authority for actual outcomes and attempt counts; interrupted attempts remain present when the same configuration is resumed. Each successful configuration retains its entire trace, including every proposed/random chart and four actual stage endpoints per rotation.

The executable study source identity is `4282fb6588006917a0fdd94339113c4799d1f26cd5bb37f0e67a3282bc764ed8`. All source bytes and instructions for using them are retained under `source_snapshots/<hash>/`. The recorded Git commit is the full pre-revision HEAD with `gitDirty=true`; the effective source fingerprint identifies the actual revised code. Paper and website files are excluded from the executable fingerprint. Later integrity hardening can therefore be distinguished from the precise code that produced these results.

The three commands below were run concurrently in the pinned `.venv` environment. The machine exposes eight logical CPUs, and each CP solve requests eight workers. Timings include contention and must not be interpreted as isolated benchmarks. Two root-controlled processes exited with signal15 before recording a terminal result. Exact-configuration resumption preserved their `interrupted_unfinished` attempts and started new attempts; the cause of those signals was not established. Neither interruption is described as a mathematical infeasibility or a solver timeout.

```bash
.venv/bin/python -u sim/experiments.py \
  --seed-values 1,3,5,7,9 --scenarios honest,coalition_min4 \
  --skip-budgets --skip-communities --out results/verified_core_a.json

.venv/bin/python -u sim/experiments.py \
  --seed-values 2,4,6,8,10 --scenarios honest,coalition_min4 \
  --skip-budgets --skip-communities --out results/verified_core_b.json

.venv/bin/python -u sim/experiments.py \
  --seed-values 7 \
  --scenarios coalition_none,coalition_stratified,coalition_shared_anchor,coalition_screened \
  --anneal-budgets 100000,900000 --cpsat-budgets 0.1,1.0 \
  --horizons 5,32 --communities 0.6:0.3,1.0:0.0 \
  --out results/verified_sensitivity.json
```

Primary runs use16 rotations,300,000 annealing iterations, CP improvement budget3.5 deterministic-time units, pre-feasibility budget20, eight workers, and a solver seed equal to the population seed (recorded separately). Actual per-rotation solver seeds are `1000*solverSeed + zeroBasedRotation`. Random baseline seeds are derived independently as strings. The default population is257, split132/125; lists have at most8; μ=ω=0. Sensitivities change only their named setting relative to honest population7. Annealing and CP defaults are supplied by the existing honest seed7 reference rather than repeated and counted again. Community and horizon evidence is one-population descriptive sensitivity, not a multi-seed robustness claim.

After all attempts terminate:

```bash
.venv/bin/python paper/assemble_evidence.py --retained-source
.venv/bin/python results/verification/verify_traces.py \
  results/verified_experiments.json --out results/verification/combined_charts.json
.venv/bin/python results/verification/verify_privacy.py \
  results/verified_experiments.json --out results/verification/combined_privacy.json
.venv/bin/python paper/make_tables.py
.venv/bin/python paper/make_figures.py --retained-source
```

Assembly independently verifies trace checksums, exact inputs, source bytes, configuration fingerprints and cached summaries. `--retained-source` verifies archived source bytes and does not waive integrity checks. A partial assembly is for monitoring only; it is rejected by the final table generator. The six website references are copied from the actual seed7 default runs, not regenerated separately. Their charts and headline results therefore match the paper's reference evidence.

The chart verifier independently recomputes capacities, eligibility, support, anchors, cumulative contacts, repeats, coalition patterns, fairness summaries and all stage costs. The privacy checker uses a different CP set-cover formulation to prove exclusions of reported forced entries and recomputes the complete reported inference, with UNKNOWN recorded separately. See the generated verification JSON for actual checked counts.

Final outcome:34 recorded attempts,32 successes,2 preserved interruptions, and517 validated proposed rotations with matched random charts and2,068 recorded stage endpoints. The study generated no rule-based exclusions.

After all attempts terminated, final hardening added strict returned-configuration checks, withdrawal of summaries whose evidence no longer verifies, the public exact-length peer-universe case, and feasibility priority for a CP candidate over an invalid incumbent. The archived executable study source is unchanged. `verification/cp_priority_compatibility.json` checks all517 rotation records and shows that the last guard change alters no recorded decision. Final hardening regressions cover the newly protected cases separately.
