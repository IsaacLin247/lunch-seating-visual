# Guaranteed-Friend Lunch Seating — visual simulation

An animated, interactive website (GitHub Pages, no build step) that plays back
**precomputed traces from the real seating solver** to show a non-technical
audience how a guaranteed-friend lunch seating system behaves over a school year,
and what happens when a group tries to game it.

* `sim/` — Python: synthetic network generator, submission screens, the solver
  pipeline (pod greedy → swap repair → simulated annealing → CP-SAT with complete
  solution hints), scenario runner and JSON export.
* `docs/` — the site: plain HTML/CSS/JS, D3 (CDN), KaTeX (CDN) and DiceBear (CDN,
  client-side avatars). Reads `docs/data/*.json`.
* `tests/` — pytest: trace validity (capacities, guarantee, state alternation,
  grade partition), the coalition story in every mode, the screens on the audit's
  counterexamples (same-grade capture, K5 plus followers, non-submitter sinks,
  external anchors, odd circulants), local-search invariants, analytic baseline,
  leakage probe, plus fast unit tests of the pipeline.

## Privacy rule

**The repository and the site contain zero real student photos, names, or
personal data.** Students are `S001…S257` with grade labels only; the friendship
network is synthetic (generated from a seed); avatars are drawn in the browser
from those ids. Do not commit rosters, exports, or anything derived from real
submissions into this repo.

## The mechanism (what the site shows)

One lunch period: grade 11 (132 students) + grade 12 (125) = 257 students, 40
tables (17 seat 7, 23 seat 6). Tables reshuffle every two weeks, 16 rotations a
year, alternating **mixed-grade** and **same-grade** states (in same-grade
rotations juniors get 12×7 + 8×6 tables, seniors 5×7 + 15×6).

Each student confidentially submits **≥4 names or none** (with ≥2 same-grade
names so the guarantee is satisfiable in same-grade rotations; a list that fails
either rule counts as no submission, and the traces record how many students that
costs). Every rotation the solver enforces:

* **Hard:** every submitter sits with ≥1 listed peer (same-grade listed peers only
  in same-grade rotations).
* **Soft:** the annealing stage maximises
  E = Σ_i (1000·1[s_i ≥ 1] − max(0, s_i − 1)) − (1/10)·Σ_{co-seated (a,b)} (5·m_ab + 2·α_ab)
  with Metropolis acceptance and T geometric 2.5 → 0.02 over the full-year
  history, where s_i = listed peers at i's table, m_ab = past co-seatings of the
  pair while neither listed the other, α_ab = past co-seatings while one listed the
  other (so an incidental repeat costs 5 per prior meeting and a listed-friend
  repeat 2). The CP-SAT stage minimises 300·Σ z_i + Σ w_ab·r_ab over
  previous-rotation pairs with w_ab = 100·(5·m_ab + 2·α_ab). Tab 4 states the
  same equations.
* **Pre-solve screens, run on every rotation state's effective lists** (the
  same-grade state drops cross-grade names, which is exactly where an attack can
  hide): (1) *coercion*: a closed candidate set S (a list-closure) is flagged
  exactly when it admits no split into two closed parts that both contain a
  submitter, where a part is closed when every submitter in it keeps a listed
  peer inside it (exact enumeration up to 20 members, a small CP-SAT model above;
  sets whose submitters all have ≥3 names inside pass by Thomassen's two-disjoint-
  cycles theorem); (2) *demand*: a closed core C whose followers (students whose
  whole list lies in C) push |C| + |F(C)| past the seats of ⌊|C|/2⌋ tables makes
  the instance infeasible and is flagged. Flagged students are returned for
  diversification. Passing the screens is not a feasibility certificate: before
  each year the hard constraints alone are solved by CP-SAT for both states and the
  status (OPTIMAL / INFEASIBLE) is recorded.
* **Local-search invariants** (tested): no move that would increase the number of
  friendless submitters is ever accepted, so a feasible seating never becomes
  infeasible; repair accepts a swap only if the set of friendless submitters
  strictly shrinks; a submitter with no eligible name in a rotation is reported as
  an infeasible input rather than silently dropped.

### Scenarios / tabs

1. **The Whole Room**: random status quo vs. proposed system, side by side,
   all 16 rotations, students flying between tables; colour = outcome (green: one
   listed friend at the table, dark green: two or more, grey: none).
2. **One Student's Year**: follow any student: their table, the friend the
   guarantee delivered each rotation, the growing wall of people met, and the same
   student under random seating.
3. **Trying to Game It**: six students coordinate. *No defenses*: k=1 chains
   capture a table 16/16. *Min-4 rule*: the strongest 4-of-5 wiring found by
   exhaustive search (nobody lists member one) can never capture a table but forces
   at least two triples in every seating. *Same-grade attack*: five members list
   the next two around a cycle plus two seniors each, the sixth lists four of the
   five; the seniors vanish from the same-grade lists and all six are forced onto
   one table in every same-grade rotation (8/16). *Screens on*: the attack is
   flagged on the same-grade lists before rotation 1; the group resubmits the
   strongest passing wiring and gets triples, never a table.
4. **The Math**: a one-screen algorithm page typeset with KaTeX (CDN auto-render,
   no build step), under 150 words of prose, every equation in display mode.

Site-copy rule: no em dashes anywhere under `docs/` (`grep -rn "—" docs/` must
return nothing); `tests/test_site.py` enforces it along with the Tab 4 word budget
and the presence of every equation.

### What the charts reveal (privacy)

Seating charts leak list information. Anyone who sees all 16 charts and knows
that lists hold at most 8 names can deduce, by exact hitting-set reasoning, names
that *must* be on a student's list. `sim/privacy.py` runs that inference on every
exported trace and records the result (`trace["leakage"]`): on the committed honest
trace it recovers several hundred directed list entries with 100% precision. The
mechanism therefore does not keep lists confidential from a determined observer of
the charts; the README, site and article say so rather than claiming
non-inference.

### Cohort generator

`make_cohort(seed, mu, omega, group_size_dist=(6, 12), cross_grade_group_frac=0.0)`
partitions students into latent friend groups (sizes uniform on 6–12, within grade
unless `cross_grade_group_frac` says otherwise); with probability `omega` a student
also joins one secondary group; each of the K = 8 true friendships is drawn with
probability `mu` from the student's group(s) (popularity-weighted) and otherwise
from the grade-biased background. `mu = 1, omega = 0` gives isolated cliques,
`mu ≈ 0.6, omega ≈ 0.3` the realistic intertwined regime. The committed traces use
the default `mu = 0, omega = 0`; pass `--mu/--omega/--cross-grade-groups` to
`export_traces.py` to change it.

## Methodology write-up

`article/article.tex` is the journal-style article: the general rotating group
assignment problem with an anchor guarantee, its NP-completeness, the coercion
capability analysis (closed bipartitions, the minimum-list theorem, the exact
screen), the hybrid solver, and the school as a case study (`article/refs.bib`
holds its bibliography). `paper/methodology.tex` is the internal technical report
describing the implementation stage by stage.
`paper/make_tables.py` regenerates `macros.tex` and `tables.tex` in both folders
from `docs/data/*.json`, so every number in either PDF comes from the committed traces:

```bash
python paper/make_tables.py
(cd article && latexmk -pdf article.tex)
(cd paper && latexmk -pdf methodology.tex)
```

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt       # pinned: ortools 9.15.6755, numpy 2.5.2, pytest 9.1.1 (Python 3.14)
python sim/export_traces.py           # ~15 min on 8 cores, writes docs/data/*.json (deterministic)
pytest                                 # validates the exported traces + unit tests
python sim/experiments.py --seeds 10  # multi-seed / budget / community robustness runs -> results/experiments.json
cd docs && python -m http.server 8000 # then open http://localhost:8000
```

`export_traces.py` options: `--seed 7`, `--scenarios honest,coalition_none,…`,
`--fast` (small budgets, for smoke tests), `--wallclock` (multi-threaded CP-SAT
with a wall-clock limit, faster but not reproducible), `--mu/--omega/--cross-grade-groups`
(latent friend groups), `--short-list-policy none|pad`. The default uses CP-SAT's
deterministic interleaved search with 8 workers; re-running the export reproduces
the committed files byte for byte apart from timestamps and timings, on the pinned
versions. Every trace records the library versions and the git commit it was made
with. Per-rotation solve time is 5–13 s; the full export of five scenarios takes
about 15 minutes.

## Deploy on GitHub Pages

1. Push to GitHub. 2. Settings → Pages → *Deploy from a branch* → branch `main`,
folder `/docs`. 3. Open the published URL. Everything is static; the only network
requests after load are the D3, KaTeX and DiceBear CDNs (avatars fall back to initials
badges if the CDN is unavailable).

## Trace format (`docs/data/<scenario>.json`)

```json
{ "config": {...}, "students": [{"id":"S001","grade":11}, ...],
  "listed": [["S014","S090",...], ...],
  "hero": "S123",
  "rotations": [
    {"idx":1, "state":"mixed",
     "tables": [["S001","S045",...], ...],            // proposed system
     "tablesRandom": [[...], ...],                    // status-quo baseline
     "anchors": {"S001":"S014", ...},                 // listed peer that satisfied the guarantee
     "anchorsRandom": {...},
     "stats": {"pctGe1":100.0, "pctExactly1":99.2, "pctGe1Random":21.1,
               "meanDistinctMet":5.5, "meanDistinctMetRandom":5.5, ...},
     "coalition": {"clusters":[[...]], "maxCluster":6, "avgCluster":6.0, "intact":true}}
  ],
  "summary": {...} }
```

Every trace is validated before export: exact capacities, every submitter
satisfied in every rotation (asserted), no cross-grade tables in same-grade
rotations, alternating states.

## Notes on the solver implementation

* Per-student indicator encoding in CP-SAT (`y[i,t]` ≥1 listed peer, `z[i]` ≥2
  listed peers), no pairwise friend variables; repeat variables only for pairs
  seated together in the previous rotation. Hints cover every variable.
* Local search moves are *group swaps* built by list-closure (padded groups are
  re-closed), and every candidate move is rejected if it would increase the number
  of friendless submitters, so a feasible seating never becomes infeasible; a
  "kick and repair" compound move handles stubborn chains such as the k=1
  coalition and is kept only if it strands nobody who was satisfied.
* A hint can be complete yet infeasible and a time-limited CP-SAT solve can return
  UNKNOWN; the pipeline therefore validates every returned seating itself and never
  exports one that violates the guarantee (it raises instead). Reported solve times
  include the fallback solve when it runs.
* Reproducibility: fixed annealing iteration counts, CP-SAT deterministic
  interleaved search with 8 workers (16 workers were not repeatable in-process on
  an 8-core machine), pinned library versions, and per-trace version/commit
  metadata.
* CP-SAT's solution is accepted only if it keeps the guarantee and does not worsen
  the full-history objective (which CP-SAT cannot see); otherwise the annealed
  solution is kept. Each rotation's `stats.acceptedPhase` records which one won.
