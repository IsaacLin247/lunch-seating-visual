# Guaranteed-Friend Lunch Seating — visual simulation

An animated, interactive website (GitHub Pages, no build step) that plays back
**precomputed traces from the real seating solver** to show a non-technical
audience how a guaranteed-friend lunch seating system behaves over a school year,
and what happens when a group tries to game it.

* `sim/` — Python: synthetic network generator, submission screens, the solver
  pipeline (pod greedy → swap repair → simulated annealing → CP-SAT with complete
  solution hints), scenario runner and JSON export.
* `docs/` — the site: plain HTML/CSS/JS, D3 (CDN) and DiceBear (CDN, client-side
  avatars). Reads `docs/data/*.json`.
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
* **Soft (minimised):** students with ≥2 listed peers at their table (weight 300
  each — the goal is *one* familiar face and everyone else new), plus
  history-weighted repeat penalties: incidental repeats cost 5·m, listed-friend
  repeats 2·α (m, α = how often the pair has already shared a table). Annealing
  carries the full-year history; CP-SAT penalises previous-rotation pairs at 100×
  those weights.
* **Pre-solve screens:** (a) insularity — a student whose list-closure has size
  2–12 sits in a coercive kernel; (b) boundary — clusters with ≥3 shared names and
  ≤3 combined outward names. Flagged groups are returned for diversification.

### Scenarios / tabs

1. **The Whole Room** — random status quo vs. proposed system, side by side,
   all 16 rotations, students flying between tables; colour = outcome (green: one
   listed friend at the table, dark green: two or more, grey: none).
2. **One Student's Year** — follow any student: their table, the friend the
   guarantee delivered each rotation, the growing wall of people met, and the same
   student under random seating.
3. **Trying to Game It** — six students coordinate. *No defenses*: k=1 chains
   capture a table 16/16. *Min-4 rule*: adversarially wired 4-of-5 lists get split
   into pairs. *Screens on*: the group is flagged before rotation 1, resubmits with
   outside names, and the year plays like everyone else's.

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
requests after load are the D3 and DiceBear CDNs (avatars fall back to initials
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
