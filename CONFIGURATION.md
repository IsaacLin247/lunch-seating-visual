# Configuration reference

All options below are recorded in every trace (`config` and `config.provenance.effectiveInputs`) and enter the experiment ledger's resume fingerprint, so a changed option never reuses an old result.

## Objective (one specification for every stage)

`sim/objective.py` defines the rotation objective

```
C = extra_weight * sum_i max(0, s_i - 1) + lambda * sum_{co-seated pairs} (5 m_ab + 2 alpha_ab)
```

with `s_i` the number of present, eligible listed companions at student `i`'s table, `m_ab` the prior incidental meetings of the pair and `alpha_ab` the prior meetings while one listed the other (mutually exclusive counters). Defaults: `extra_weight = 1`, `lambda = 0.1`, repeat weights 5 and 2. The hard at-least-one requirement is not configurable.

Every weight is rational, and the implementation works with the smallest integer scaling that makes every weight integral. With the defaults the integer cost is `10 * extras + sum(5 m_ab + 2 alpha_ab)` plus `10000` per hard violation during search, and the annealing temperature runs from 25 to 0.2 (2.5 to 0.02 unscaled). CP-SAT minimises exactly the same integer cost over valid charts.

| Option | CLI | Default | Notes |
|---|---|---|---|
| penalty per extra listed companion | `--extra-weight` | `1.0` | `0.5` halves the pressure toward exactly one; `0` removes it (the guarantee stays) |
| repeat weights | `Objective(repeat_lambda, incidental_repeat, listed_repeat)` | `0.1, 5, 2` | Python API only |

## Solver

| Option | CLI | Default | Notes |
|---|---|---|---|
| method | `--method hybrid|construct_repair` | `hybrid` | `construct_repair` stops after construction and repair (companion-preserving baseline, no diversity optimisation), with the same validated fallbacks |
| annealing iterations | `--anneal-iters` | `300000` | |
| CP-SAT improvement budget | `--cpsat-time` | `3.5` | deterministic-time units (or seconds with `--wallclock` / `--wall-time`) |
| CP-SAT pairs | `--cpsat-pairs all|previous` | `all` | `all` includes every pair with nonzero history cost (exact objective); `previous` is the historical surrogate, retained only for comparison |
| CP-SAT extras | `--cpsat-extras count|indicator` | `count` | `count` is an integer extras variable per submitter (exact); `indicator` is the historical two-or-more surrogate |
| workers | `--workers` | `8` | |
| preliminary feasibility budget | `--feasibility-time` | `20.0` | per distinct set of hard constraints; a witness is validated and cached as a fallback |
| rotations | `--rotations` | `16` | alternating mixed and same-grade, starting mixed |

Benchmark at 257 students (`results/benchmarks/cpsat_formulation_257.json`): the exact formulation adds roughly one to three seconds of wall time per rotation and never worsened the incumbent, while the previous-rotation surrogate returned charts that were worse under the full objective in most rotations.

## Submissions

| Option | CLI | Default | Notes |
|---|---|---|---|
| short-list policy | `--short-list-policy review|approve|withdraw|pad` | `review` | how pending requests (nonempty lists failing the rule) are decided in simulation; `review` leaves them pending and blocks scheduling; `none` is a legacy alias of `withdraw` |
| voluntary nonsubmission | `--nonsubmit-frac` | `0.0` | fraction of generated students who submit nothing |
| list cap | `--list-cap` | none | truncate generated true-friend lists (for short-list conditions) |
| review decisions | `review_decisions={student: ...}` | none | Python API: `approve`, `withdraw`, `resubmit` with names |

Submission states: `accepted`, `pending_review`, `approved_exception`, `voluntary_nonsubmission`. An approved exception keeps the student's actual obligation.

## Attendance and staff constraints

| Option | CLI | Default | Notes |
|---|---|---|---|
| synthetic absence rate | `--absence-rate` | `0.0` | per student and rotation, deterministic in the seed |
| explicit attendance | `attendance={rotation: [ids]}` | none | Python API |
| conflict policy | `--conflict-policy stop|waive` | `stop` | `stop` raises an explicit conflict listing the students; `waive` records a per-rotation obligation waiver labelled as a simulation policy |
| waivers | `waivers={rotation: {student: reason}}` | none | Python API |
| staff constraints | `staff={"prohibitedPairs": [...], "allowedTables": {...}, "tableTargets": [...]}` | none | Python API and `make_all(staff=...)` |

Occupancy targets: absences reduce table targets one seat at a time, largest tables first within the admissible grade pool, never below two seats while another table can shrink; a table closes only when the pool is too small.

## Screening budgets

`sim/screens.ScreenBudget` (Python API `screen_budget={...}`):

| Field | Default | Meaning |
|---|---|---|
| `closure_cap` | 64 | largest reachable closure examined |
| `exact_limit` | 20 | exhaustive closed-bipartition decision up to this size |
| `target_core_cap` | 12 | largest strongly connected core examined |
| `target_candidate_limit` | 256 | cores examined after deduplication |
| `deterministic_time` | 10 | CP-SAT budget per relaxed candidate |
| `separation_time` | 10 | CP-SAT budget per full-model separation test |
| `full_model_limit` | 32 | full-model tests per state |
| `full_model_group_cap` | 12 | largest group tested with the full model |
| `full_model_policy` | `risk` | `risk`: unresolved, proved-coercive and anchor-exposed candidates; `all`; `none` |

Every report records the budget and the numbers discovered, examined and skipped. Coverage is never complete.

## Outputs

- `python sim/export_traces.py` writes website traces (six reference scenarios); `--scenarios` may add `infeasible_demand`, which is proven infeasible and produces no chart.
- `python sim/experiments.py` runs the ledgered study; `python sim/evaluate_methods.py` runs the method comparison grid (category `evaluation`).
- `python sim/student_export.py TRACE --rotation R` writes the student-facing chart; `--history` is an explicit opt-in.
- `python paper/make_evaluation.py` summarises the evaluation ledger into `results/evaluation_summary.json` and LaTeX tables.
