# Guaranteed-Friend Lunch Seating: research demonstrator

A static GitHub Pages website plays back **precomputed, validated charts from the Python seating solver** on a synthetic school. It compares a random baseline, follows individual students, and illustrates strategic submissions. The browser animates transitions between saved charts and replays actual construction, repair, annealing, and final endpoints. It does not run optimization or claim to show every internal search move.

- `sim/`: synthetic generator, submission states and review decisions, attendance rosters, hard-constraint validation, effective-graph and full-model screens, the hybrid solver with validated fallbacks, adversarial constructions, analytic baseline, output-leakage inference, outcome metrics, and the experiment and evaluation runners.
- `docs/`: accessible HTML/CSS/JavaScript site, synthetic trace data, the downloadable article, and `docs/policy/` (draft submission notice, data-handling policy, administrator workflow, pilot evaluation plan).
- `CONFIGURATION.md`: every option, its default, and what it changes.
- `paper/audit_resolution.md`: finding-by-finding corrections and explicit remaining research limits, including the 11 September 2026 revision.
- `article/article.tex`: current formal research manuscript. `paper/make_tables.py` and `paper/make_evaluation.py` generate its empirical tables from retained evidence.
- `tests/`: mathematical regressions, screen outcomes, solver invariants, fallback and cache behaviour, submission and attendance handling, exact CP-SAT scoring, separation tests, trace validity, metrics, leakage, student-facing exports, experiment provenance, and website contracts.

## Current specification and limits

The 13 September 2026 publication audit corrects manuscript scope, rebuilds current tables and PDFs, and adds code regressions. The primary 32-run study is complete, but the method-comparison ledger is explicitly partial (48 attempts, 31 successful traces, two unfinished records); it does not complete the planned three-population grid. Retained traces identify the 11 September executable source and are not reruns of subsequent repairs. See `paper/publication_audit.md` for findings and remaining submission requirements.

`sim/` and the revised article specify the current implementation. Historical proposal figures describe an older objective and must not be used to validate this version. The original canonical solver and original experiment files supplied for the first audit remain unavailable; this repository is the independently implemented and tested version. The study of 8 September 2026 (`results/verified_*.json`) is retained as historical evidence of the previous implementation; results of the revised implementation come from `results/revised_*.json`.

The case study has 257 students (132 grade 11, 125 grade 12), forty tables (seventeen of size seven, twenty-three of size six), and sixteen rotations alternating mixed and same-grade seating. During same-grade rounds, grade 11 uses twelve seven-seat and eight six-seat tables; grade 12 uses five seven-seat and fifteen six-seat tables.

Students submit four to eight distinct names or no list, with at least two same-grade names for this schedule. Lists are directed: naming a student does not imply reciprocal friendship. A nonempty list that fails the rule is kept as a **request pending review**; it is never silently turned into nonsubmission and never padded by default. Submission states are `accepted`, `pending_review`, `approved_exception` (a reviewed short list that keeps its real obligation), and `voluntary_nonsubmission`.

Every released chart seats every present student once, meets its occupancy targets within physical capacities, respects grade eligibility and staff constraints, and gives each obligated student **at least one present, eligible listed companion**. Exactly one is an optimization preference. Unlisted tablemates may already be familiar, and "met" in the results means "seated together." A valid chart is a guarantee for that chart; bounded search does not promise a valid chart for every input.

### Scheduling outcomes

Every run ends in exactly one of `scheduled`, `review_required` (pending requests, screen returns, unresolved checks, or attendance conflicts), `proven_infeasible` (a CP-SAT infeasibility certificate), or `unknown` (bounded search found no valid chart and no validated fallback existed; not a proof). Within a scheduled year each rotation is `optimized`, `incumbent` (a validated cached chart that no search result beat), or `fallback` (the search never reached a valid chart of its own). A chart is called optimal only when CP-SAT proved it under the exact objective.

### Solver pipeline

1. **Classify submissions and screen effective lists for each state.** Cross-grade names are ineligible in same-grade rounds. Candidate coercion tests include reachable closures and targeted cores exposed by single-anchor deletion; high-risk candidates get a **full-model separation test** (the complete assignment model plus "the group occupies at least two tables"), whose outcomes are a validated separating chart, a forcing certificate under the current constraints, or unresolved. Demand bounds use only admissible grade capacities. Budgets are configurable and coverage is reported. Passage is neither a complete anti-collusion guarantee nor a feasibility certificate.
2. **Certify feasibility and cache the witness.** For each distinct set of hard constraints (roster, obligations, eligibility, capacities, targets, staff constraints) a CP-SAT solve either supplies a witness that is validated independently and cached, proves infeasibility, or returns UNKNOWN. Meeting history changes scores, not validity, so cached charts stay reusable and are rescored.
3. **Build and repair.** Greedy pods are packed into compatible tables. Accepted rescue moves strictly reduce the friendless set while preserving already-satisfied submitters. Repair can terminate without reaching feasibility.
4. **Anneal.** Capacity-preserving, grade-compatible group swaps minimize the canonical objective

   `C = sum_i max(0, s_i - 1) + 0.1 sum_co-seated_pairs (5 m_ab + 2 alpha_ab)`

   plus 1000 per hard violation during search. `s_i` counts present eligible listed tablemates, `m_ab` prior incidental meetings, and `alpha_ab` prior meetings while either student listed the other (disjoint counters). The penalty per extra companion is configurable (`--extra-weight`). Accepted moves cannot increase the violation count. If construction fails to reach feasibility, annealing restarts from the validated incumbent.
5. **Polish, guard, and validate.** CP-SAT minimizes exactly `10 sum_i e_i + sum_pairs (5 m_ab + 2 alpha_ab) r_ab` with an integer extras variable per submitter and every pair with nonzero history, seeded by the best of annealing and the incumbent. A returned chart is rescored independently and replaces a valid incumbent only if it is valid and no worse. If every stage fails, the validated fallback is released with status `fallback`. Nothing invalid is ever released; every chart passes `Problem.validate` before release.

No result here proves optimal seating over a year, complete attack resistance, student benefit, or deployment readiness.

## Website views and adversarial scenarios

1. **The Whole Room:** proposed and random charts use identical capacities and grade schedules. Metrics show listed-peer coverage and cumulative distinct tablemates. The saved release status, accepted phase and CP-SAT status are visible.
2. **One Student's Year:** an accessible student selector shows the current anchor, all encountered tablemates, and the same student's random-baseline history. "Selected anchors" counts one recorded witness per rotation, which can differ from all listed peers encountered.
3. **Trying to Game It:** scenario controls and coalition membership are derived from trace metadata. Diagrams distinguish eligible coalition names, eligible outside names, and submitted names that are ineligible in the selected round. Structural statements appear separately from outcomes calculated over the saved year.
4. **The Algorithm:** replay the actual recorded construction, repair, annealing, and final assignments for any selected honest rotation, with violation counts, surplus peers, energy, and stage time. Early snapshots can be invalid and are labelled accordingly. Read the explicit constraints, guarded repair, annealing, exact CP-SAT polishing, fallbacks, screening limits, output leakage, and provenance.

The adversarial cases are:

| Scenario | Structural claim and scope |
|---|---|
| `coalition_none` | A one-name directed cycle forces its six members together. It violates the minimum-list rule. |
| `coalition_min4` | The six-member internal omission star permits 3+3, 4+2, and 6. Its member-weighted mean cluster is at least 3. Exhaustive search is restricted to the four-of-five internal wiring family. It cannot force all six together solely through these lists, although a shared table is allowed. |
| `coalition_stratified` | Cross-grade padding hides an unsplittable five-member core plus a follower. All six must share a table in same-grade rounds. Screens are disabled to display the attack. |
| `coalition_shared_anchor` | Seven cycle members each name a successor, a common outside junior, and two seniors. At capacity seven the anchor cannot accompany the whole cycle, forcing a full coalition table in same-grade rounds. Revised detection is recorded diagnostically; enforcement is disabled to display the attack. |
| `coalition_screened` | The six-member stratified submission is returned and replaced with a specified omission-star submission. This is one modeled response, not a globally optimal attack or proof of universal resistance. |
| `infeasible_demand` (not on the site) | Five mutual core members plus ten followers who list only the core; CP-SAT proves infeasibility and nothing is scheduled. Used by the evaluation grid. |

The exported charts determine observed patterns and frequencies. Neither "at least two triples in every chart" nor "never a shared table" correctly describes the omission-star structure. Recurring co-seated groups across rotations are reported as diagnostics only; recurring co-seating is not evidence of intent.

## Synthetic data, privacy, and inference

The repository contains no real rosters, photos, names, or submitted lists. Anonymous IDs and avatars describe generated students only. Do not add real school submissions or identifiable derivatives to this public repository. The demonstration data must stay synthetic.

Confidential collection does **not** prevent inference from published charts. `sim/privacy.py` uses exact hitting-set reasoning to infer names required by every list compatible with the observed tablemate sets and a public list cap; its stated assumptions include known submitter identities and fixed lists across the observed horizon. Two further analyses are recorded in every trace: the worst logical forcing when only the current chart is distributed (`leakage.currentOnlyDistribution`), and the co-seating exposure statistic (`leakage.coseatingExposure`), the fraction of obligated students whose most frequent tablemate is a listed peer. A single sufficiently occupied chart forces no individual name under the stated model, and removing a public cap removes this form of logical forcing; an observer can still accumulate co-seating counts across rotations for statistical inference, so none of these measures guarantees confidentiality.

Student-facing distribution uses `python sim/student_export.py TRACE --rotation R`, which contains the assignment of one rotation and nothing private; history is an explicit opt-in. The static site has no access control, and hiding fields in a browser is not protection; the infrastructure a private distribution needs is listed in `docs/policy/data_handling_policy.md`.

The generator samples popularity-weighted, grade-biased friendships and optional latent communities. `mu` controls within-community draws, `omega` overlapping membership, and `cross_grade_group_frac` cross-grade groups. These are synthetic sensitivity parameters, not empirically calibrated estimates. A classroom pilot and student-welfare conclusions require separate evidence; `docs/policy/pilot_evaluation_plan.md` outlines one.

## Run and reproduce

Use the Python version recorded by the artifact you wish to reproduce; dependencies are pinned in `requirements.txt`.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-paper.txt
pytest
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000`. Export supports `--seed`, `--scenarios`, `--anneal-iters`, `--cpsat-time`, `--workers`, `--rotations`, `--mu`, `--omega`, `--cross-grade-groups`, `--short-list-policy review|approve|withdraw|pad`, `--nonsubmit-frac`, `--list-cap`, `--method hybrid|construct_repair`, `--extra-weight`, `--absence-rate`, `--conflict-policy stop|waive`, `--cpsat-pairs all|previous`, and `--fast`. Use `--out` for separate experiments so smoke tests do not replace publication traces. `--wallclock` switches to timing-dependent CP-SAT search. See `CONFIGURATION.md` for every option.

The default annealing budget is 300,000 iterations with 3.5 deterministic CP-SAT time units and eight workers per rotation. Deterministic time units are not elapsed seconds. Every trace records its effective source identity, generator configuration, population and solver seeds, submission states, attendance, staff constraints, objective weights, library versions, and solver budgets.

The experiment runner writes a pre-solve attempt ledger, terminal outcomes (`success`, `review_required`, `infeasible_input`, `unknown`, `error`, interruptions), and retained full traces. A small explicit batch is:

```bash
python sim/experiments.py --seed-values 1,2 --scenarios honest,coalition_min4 --skip-budgets --skip-communities --out results/example_experiments.json
python sim/evaluate_methods.py --seed-values 1 --conditions reference,absences --out results/example_evaluation.json
```

The complete study uses the commands in `results/STUDY.md`. `bash paper/build.sh` verifies retained evidence and builds both PDFs and the site download.

The method comparison (`sim/evaluate_methods.py`, summarised by `paper/make_evaluation.py`) compares the hybrid solver with a companion-preserving construction-and-repair baseline and the matched random baseline on common populations, capacities, eligibility, and attendance inputs, including short and concentrated lists, voluntary nonsubmission and approved exceptions, absences, coalition examples, a proven infeasible instance, and time-limited budgets. The school's current seating procedure has no written rule specification available to this project, so it is not modelled; that gap is stated rather than filled by assumption.

## Publish on GitHub Pages

Serve branch `main`, folder `/docs`, in the repository's Pages settings. Update `docs/article.pdf` from the compiled article and deploy the source and generated traces together. `docs/data/manifest.json` lists the scenario files loaded by the page; `index.json` supplies an additional export inventory. The site ships local copies of D3, KaTeX (including fonts), and a small DiceBear avatar bundle with an initials fallback. Runtime scripts, fonts, and styles load from the site itself; pinned versions, asset hashes, and licenses are retained in `docs/vendor/`. Graphs and pipeline visuals use native HTML/SVG; reduced-motion preferences are respected.

Site-copy convention: no em dashes in text assets under `docs/`. Binary PDFs are excluded from this text convention. `tests/test_site.py` checks structural and behavioral website contracts; numeric and chart consistency is validated separately by trace tests.

The page entry point, authored module imports, and stylesheet use one matching `?v=` release suffix. Bump that suffix together when publishing changes to those assets so returning browsers load compatible versions of every view. `tests/test_site_assets.py` checks the module graph and cached-tab upgrade behavior.

## Directory portraits for a presentation

From any of the four tabs, click **Load directory** and select the existing `student_directory` folder, including its grade HTML exports and saved `_files` folders. A browser folder picker is required each time you load a fresh page; the site cannot automatically read files from your computer. The browser may call the selection an “upload,” but this feature reads the files locally and sends none to a server.

The current simulation has 257 synthetic slots: 132 in grade 11 and 125 in grade 12. Portraits fill those slots once each within the matching grade. The supplied directory provides **252 matching portraits**, with anonymous avatars for five missing images. Grades 9 and 10 are imported but are not used by this existing simulation.

- One folder selection supplies the same portrait for each simulation ID across the whole room, student profiles and companion lists, met/ghost rows, coalition rooms and diagrams, and algorithm-stage playback.
- **Room zoom** enlarges canvas faces on every tab. Scroll within a room when zoomed.
- Click or tap a table, or use the table selectors, to view large portraits with directory names and their simulation IDs. Canvas keyboard controls also support arrows, Enter/Space, and Escape. The initial view fits the room and keeps the enlarged table closed.
- **Remove directory** is available from every tab. It clears all names and portrait views, including hidden tabs, and revokes their image URLs. Refreshing or leaving the page clears the local selection as well.

The photos are visual stand-ins in a page labeled **Simulation**. Seating, companion choices, and outcome statistics remain the original simulated data. Directory names are displayed locally alongside their matching portraits; contact details and real submitted lists are not displayed. Companion lists and coalition behavior are generated examples, never claims about the pictured students. Names and portraits use the same stable ordering: sort simulation IDs and directory IDs separately within each grade, then pair corresponding positions. Missing images retain their names and never shift subsequent matches. Names appear in table cards, student pickers, profiles, companion lists, tooltips, and coalition diagrams; simulation IDs remain available for reference. This is a presentation mapping, not a claim that the synthetic network describes those students. Clearing or replacing a directory preserves the selected student, scenario, rotation, and algorithm stage. Saved directory scripts are never run; photos are decoded into new JPEGs without their original metadata.

The compact interface puts charts and controls first. Directory status is a short photo count, with import notes expandable when needed. Rotation, scenario, and algorithm explanations are available in closed details panels; the paper and trace references are under **Algorithm → How it works**.

Only website code and library assets belong in `docs/`. Do not copy the school directory or generated portrait files into the public repository. The dean loads the directory locally on the presentation computer; the public link does not contain the names or photos.

Optional browser checks use synthetic directory fixtures, verify that the portrait layer does not change solver results, and check cleanup and network boundaries:

```sh
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest tests/test_site.py tests/test_site_assets.py tests/test_room_portraits.py -q
.venv/bin/python tests/browser_portraits.py
node tests/test_avatar_mapping.mjs
node tests/test_directory_names.mjs
```

The browser script can also check aggregate counts from the uploaded folder with `--real-directory ../student_directory`. It does not save photographs or names. Renderer browser tests skip when Playwright or Chromium is unavailable.

## Trace format

`docs/data/<scenario>.json` contains:

- `config`: scenario rules, submission rules and states, coalition membership, table layout, objective and weights, generator and solver settings, attendance and staff constraints, source provenance, feasibility status and cache keys per state, screening reports with budgets and full-model results, the fallback cache summary, and the scheduling status.
- `students` (with submission state), `listed`, and optional `listedInitial`: anonymous IDs, grades, final obligations and initial submissions for the resubmission example.
- `rotations`: proposed and random tables over the present roster, occupancy targets, absences and waived obligations, one selected anchor per satisfied submitter, independently checkable statistics, release status and validation, coalition clusters, and `pipeline` stage snapshots with actual tables and costs.
- `outcomes`: per-student and aggregate individual outcomes for the proposed and random charts, and participation.
- `recurringGroups`, `fairness`, `leakage`, and `summary`: derived year-level diagnostics and chart-inference results.

The website reads these artifacts without changing them. The stored tables are the evidence for the displayed outcomes.
