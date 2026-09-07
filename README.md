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
  grade partition), coalition capture in mode 1, scatter in mode 2, screens in
  mode 3, plus fast unit tests of the pipeline.

## Privacy rule

**The repository and the site contain zero real student photos, names, or
personal data.** Students are `S001…S257` with grade labels only; the friendship
network is synthetic (generated from a seed); avatars are drawn in the browser
from those ids. Do not commit rosters, exports, or anything derived from real
submissions into this repo.

## The mechanism (what the site shows)

One lunch period: grade 11 (132 students) + grade 12 (125) = 257 students, 40
tables (17 seat 7, 23 seat 6). Tables reshuffle every two weeks — 16 rotations a
year — alternating **mixed-grade** and **same-grade** states (in same-grade
rotations juniors get 12×7 + 8×6 tables, seniors 5×7 + 15×6).

Each student confidentially submits **≥4 names or none** (with ≥2 same-grade
names so the guarantee is satisfiable in same-grade rotations). Every rotation the
solver enforces:

* **Hard:** every submitter sits with ≥1 listed peer (same-grade listed peers only
  in same-grade rotations).
* **Soft:** the annealing stage maximises
  E = Σ_i (1000·1[s_i ≥ 1] − max(0, s_i − 1)) − (1/10)·Σ_{co-seated (a,b)} (5·m_ab + 2·α_ab)
  with Metropolis acceptance and T geometric 2.5 → 0.02 over the full-year
  history (s_i = listed peers at i's table, m_ab = co-seatings so far, α_ab = those
  where one listed the other). The CP-SAT stage minimises 300·Σ y²_i + Σ w_ab·r_ab
  over previous-rotation pairs with w_ab = 100·(5·m_ab + 2·α_ab). Tab 4 states the
  same equations.
* **Pre-solve screen (coercion capability, exact):** candidate sets come from two
  cheap detectors, insular kernels (list-closure size 2–12) and boundary clusters
  (≥3 shared names, ≤3 combined outward names). A candidate S is flagged exactly
  when S admits no bipartition into two closed parts of size ≥2 (a part is closed
  when every member keeps a listed peer inside it), which is decided by exact
  enumeration over the 2^|S| splits. Flagged sets, together with the kernel that
  contains them, are returned for diversification.

### Scenarios / tabs

1. **The Whole Room**: random status quo vs. proposed system, side by side,
   all 16 rotations, students flying between tables; colour = outcome (green: one
   listed friend at the table, dark green: two or more, grey: none).
2. **One Student's Year**: follow any student: their table, the friend the
   guarantee delivered each rotation, the growing wall of people met, and the same
   student under random seating.
3. **Trying to Game It**: six students coordinate. *No defenses*: k=1 chains
   capture a table 16/16. *Min-4 rule*: adversarially wired 4-of-5 lists get split
   into pairs. *Screens on*: the group is flagged before rotation 1, resubmits with
   outside names, and the year plays like everyone else's.
4. **The Math**: a one-screen algorithm page typeset with KaTeX (CDN auto-render,
   no build step), under 150 words of prose, every equation in display mode.

Site-copy rule: no em dashes anywhere under `docs/` (`grep -rn "—" docs/` must
return nothing); `tests/test_site.py` enforces it along with the Tab 4 word budget
and the presence of every equation.

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

`paper/article.tex` is the journal-style article: the general rotating group
assignment problem with an anchor guarantee, its NP-completeness, the coercion
capability analysis (closed bipartitions, the minimum-list theorem, the exact
screen), the hybrid solver, and the school as a case study. `paper/methodology.tex`
is the internal technical report describing the implementation stage by stage.
`paper/make_tables.py` regenerates `paper/macros.tex` and `paper/tables.tex` from
`docs/data/*.json`, so every number in the PDF comes from the committed traces:

```bash
python paper/make_tables.py && (cd paper && latexmk -pdf article.tex methodology.tex)
```

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python sim/export_traces.py          # ~12 min on 8 cores, writes docs/data/*.json (deterministic)
pytest                                # validates the exported traces + unit tests
cd docs && python -m http.server 8000 # then open http://localhost:8000
```

`export_traces.py` options: `--seed 7`, `--scenarios honest,coalition_none,…`,
`--fast` (small budgets, for smoke tests), `--wallclock` (multi-threaded CP-SAT
with a wall-clock limit — faster but not bit-reproducible; the default uses
CP-SAT's deterministic interleaved search so the same seed always yields the
same traces). Per-rotation solve time is 5–12 s (annealing ≈4 s, CP-SAT ≈3–7 s);
the full export of four scenarios × 16 rotations takes about 12 minutes.

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
* Local search moves are *group swaps* built by list-closure so the guarantee is
  never broken mid-move; a "kick and repair" compound move handles stubborn
  chains such as the k=1 coalition.
* CP-SAT's solution is accepted only if it keeps the guarantee and does not worsen
  the full-history objective (which CP-SAT cannot see); otherwise the annealed
  solution is kept. Each rotation's `stats.acceptedPhase` records which one won.
