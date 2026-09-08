# Guaranteed-Friend Lunch Seating: research demonstrator

A static GitHub Pages website plays back **precomputed, validated charts from the Python seating solver** on a synthetic school. It compares a random baseline, follows individual students, and illustrates strategic submissions. The browser animates transitions between saved charts and replays actual construction, repair, annealing, and final endpoints. It does not run optimization or claim to show every internal search move.

- `sim/`: synthetic generator, effective-graph screens, hybrid solver, adversarial constructions, analytic baseline, output-leakage inference, and experiment runner.
- `docs/`: accessible HTML/CSS/JavaScript site, trace data and the downloadable article. Scenario controls, coalition sizes, outcomes, and timeline lengths come from loaded traces.
- `paper/audit_resolution.md`: finding-by-finding corrections and explicit remaining research limits.
- `article/article.tex`: current formal research manuscript. `paper/make_tables.py` generates its empirical tables from retained evidence.
- `tests/`: mathematical regressions, screen outcomes, solver invariants, trace validity, metrics, leakage, experiment provenance, and website contracts.

## Current specification and limits

`sim/solver.py`, `sim/screens.py`, and the revised article specify the current implementation. Historical proposal figures describe an older objective and must not be used to validate this version. The original canonical solver and original experiment files supplied for the first audit remain unavailable; this repository is the independently implemented and tested version.

The case study has 257 students (132 grade 11, 125 grade 12), forty tables (seventeen of size seven, twenty-three of size six), and sixteen rotations alternating mixed and same-grade seating. During same-grade rounds, grade 11 uses twelve seven-seat and eight six-seat tables; grade 12 uses five seven-seat and fifteen six-seat tables.

Students submit four to eight distinct names or no list, with at least two same-grade names for this schedule. Lists are directed: naming a student does not imply reciprocal friendship. In the default synthetic generator, an authentic list that fails the minimum rule becomes an explicitly recorded opt-out; names are not silently invented. This policy exposes an eligibility cost and is not evidence of fairness.

Every exported chart fills all tables, seats every student once, respects grade eligibility, and gives each submitter **at least one eligible listed peer**. Exactly one is an optimization preference. Unlisted tablemates may already be familiar, and “met” in the results means “seated together.” A valid chart is a guarantee for that chart; bounded search does not promise a valid chart for every input.

### Solver pipeline

1. **Screen effective lists for each state.** Cross-grade names are ineligible in same-grade rounds. Candidate coercion tests include reachable closures and targeted cores exposed by single-anchor deletion. Demand bounds use only admissible grade capacities. Proven flags and unresolved searches are separate outcomes. Candidate passage is neither a complete anti-collusion guarantee nor a feasibility certificate.
2. **Check hard feasibility.** A CP-SAT witness proves feasibility; INFEASIBLE proves impossibility for that model; UNKNOWN means the bounded check did not decide. Search may continue after UNKNOWN, but only a subsequently validated chart can establish feasibility.
3. **Build and repair.** Greedy pods are packed into compatible tables. Accepted rescue moves strictly reduce the friendless set while preserving already-satisfied submitters. Repair can terminate without reaching feasibility.
4. **Anneal.** Capacity-preserving, grade-compatible group swaps minimize

   `C = 1000 |V| + sum_i max(0, s_i - 1) + 0.1 sum_co-seated_pairs (5 m_ab + 2 alpha_ab)`.

   Here `V` is the friendless submitter set, `s_i` counts eligible listed tablemates, `m_ab` counts prior incidental meetings, and `alpha_ab` counts prior meetings while either student listed the other. Histories are disjoint, so per-prior-meeting costs are 0.5 and 0.2. Temperature decreases geometrically from 2.5 to 0.02. Accepted moves cannot increase the violation count; before feasibility, the identities of friendless students may change. Padded groups are re-closed.
5. **Polish and validate.** A complete hint seeds bounded CP-SAT search. Its surrogate minimizes `300 sum_i z_i + 100 sum_previous_pairs (5 m_ab + 2 alpha_ab) r_ab`, with `z_i` indicating two or more listed peers. It counts affected students instead of every extra peer and selects repeat pairs from the previous rotation rather than the full history. Accept a polished chart only when it is feasible and does not worsen the full-history score. A fallback feasibility solve can run. Export no chart if validity cannot be established; report the failure.

No result here proves optimal seating, complete attack resistance, student benefit, or deployment readiness.

## Website views and adversarial scenarios

1. **The Whole Room:** proposed and random charts use identical capacities and grade schedules. Metrics show listed-peer coverage and cumulative distinct tablemates. The saved solver status and accepted phase are visible.
2. **One Student's Year:** an accessible student selector shows the current anchor, all encountered tablemates, and the same student's random-baseline history. “Selected anchors” counts one recorded witness per rotation, which can differ from all listed peers encountered.
3. **Trying to Game It:** scenario controls and coalition membership are derived from trace metadata. Diagrams distinguish eligible coalition names, eligible outside names, and submitted names that are ineligible in the selected round. Structural statements appear separately from outcomes calculated over the saved year.
4. **The Algorithm:** replay the actual recorded construction, repair, annealing, and final assignments for any selected honest rotation, with violation counts, surplus peers, energy, and stage time. Early snapshots can be invalid and are labelled accordingly. Read the explicit constraints, guarded repair, annealing, bounded CP-SAT polishing, screening limits, output leakage, and provenance. The former 150-word restriction was removed so the displayed algorithm can state its necessary conditions accurately.

The adversarial cases are:

| Scenario | Structural claim and scope |
|---|---|
| `coalition_none` | A one-name directed cycle forces its six members together. It violates the minimum-list rule. |
| `coalition_min4` | The six-member internal omission star permits 3+3, 4+2, and 6. Its member-weighted mean cluster is at least 3. Exhaustive search is restricted to the four-of-five internal wiring family. It cannot force all six together solely through these lists, although a shared table is allowed. |
| `coalition_stratified` | Cross-grade padding hides an unsplittable five-member core plus a follower. All six must share a table in same-grade rounds. Screens are disabled to display the attack. |
| `coalition_shared_anchor` | Seven cycle members each name a successor, a common outside junior, and two seniors. At capacity seven the anchor cannot accompany the whole cycle, forcing a full coalition table in same-grade rounds. Revised detection is recorded diagnostically; enforcement is disabled to display the attack. |
| `coalition_screened` | The six-member stratified submission is returned and replaced with a specified omission-star submission. This is one modeled response, not a globally optimal attack or proof of universal resistance. |

The exported charts determine observed patterns and frequencies. Neither “at least two triples in every chart” nor “never a shared table” correctly describes the omission-star structure.

## Synthetic data, privacy, and inference

The repository contains no real rosters, photos, names, or submitted lists. Anonymous IDs and avatars describe generated students only. Do not add real school submissions or identifiable derivatives to this public repository.

Confidential collection does **not** prevent inference from published charts. `sim/privacy.py` uses exact hitting-set reasoning to infer names required by every list compatible with the observed tablemate sets and a public list cap. Its stated assumptions include known submitter identities and fixed lists across the observed horizon. Each trace reports forced directed entries, affected students, and the precise inference assumptions. Recovering all actual entries from a short private list is reported separately from proving that a complete list is uniquely determined.

The generator samples popularity-weighted, grade-biased friendships and optional latent communities. `mu` controls within-community draws, `omega` overlapping membership, and `cross_grade_group_frac` cross-grade groups. These are synthetic sensitivity parameters, not empirically calibrated estimates. The article identifies the configurations actually tested and records exclusions and outcome tails. A classroom pilot and student-welfare conclusions require separate evidence and an explicit institutional exception process.

## Run and reproduce

Use the Python version recorded by the artifact you wish to reproduce; dependencies are pinned in `requirements.txt`.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-paper.txt
pytest
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000`. Export supports `--seed`, `--scenarios`, `--anneal-iters`, `--cpsat-time`, `--workers`, `--rotations`, `--mu`, `--omega`, `--cross-grade-groups`, `--short-list-policy none|pad`, and `--fast`. The optional padding policy changes the declared synthetic submissions; it is not the default. Use `--out` for separate experiments so smoke tests do not replace publication traces. `--wallclock` switches to timing-dependent CP-SAT search.

The default annealing budget is 300,000 iterations with 3.5 deterministic CP-SAT time units and eight workers per rotation. Deterministic time units are not elapsed seconds. Every trace records its effective source identity, generator configuration, population and solver seeds, library versions, and solver budgets. Timings and timestamps can vary; reproducibility claims apply to the pinned tested configuration and must be checked against its effective source fingerprint, not HEAD alone.

The experiment runner writes a pre-solve attempt ledger, terminal outcomes, and retained full traces. Resume keys include effective configuration and source identity. A small explicit batch is:

```bash
python sim/experiments.py --seed-values 1,2 --scenarios honest,coalition_min4 --skip-budgets --skip-communities --out results/example_experiments.json
```

The complete publication study uses the commands in `results/STUDY.md`. `bash paper/build.sh` verifies retained evidence and builds both PDFs and the site download. Its main steps are:

```bash
python paper/assemble_evidence.py --retained-source
python paper/make_tables.py
python paper/make_figures.py --retained-source
cd article
latexmk -pdf article.tex
```

Use `python sim/experiments.py --help` for budget, community, and horizon sensitivity options. `results/verified_experiments.json` is the new attempt-level inventory; historical summary-only evidence is not equivalent to a validated attempt ledger. Manuscript figures must be regenerated from a chosen completed inventory, with actual successes, failures, and unfinished attempts identified.

## Publish on GitHub Pages

Serve branch `main`, folder `/docs`, in the repository's Pages settings. Update `docs/article.pdf` from the compiled article and deploy the source and generated traces together. `docs/data/manifest.json` lists the scenario files loaded by the page; `index.json` supplies an additional export inventory. The site uses D3 and KaTeX from CDNs and client-side DiceBear avatars with an initials fallback. Graphs and pipeline visuals use native HTML/SVG; reduced-motion preferences are respected.

Site-copy convention: no em dashes in text assets under `docs/`. Binary PDFs are excluded from this text convention. `tests/test_site.py` checks structural and behavioral website contracts; numeric and chart consistency is validated separately by trace tests.

## Trace format

`docs/data/<scenario>.json` contains:

- `config`: scenario rules, coalition membership, table layout, generator and solver settings, source provenance, feasibility status, and available screen diagnostics.
- `students`, `listed`, and optional `listedInitial`: anonymous IDs, grades, final submissions and initial submissions for the resubmission example.
- `rotations`: proposed and random tables, one selected anchor per satisfied submitter, independently checkable statistics, coalition clusters, solver status, accepted phase, and `pipeline` stage snapshots with actual tables and costs.
- `summary` and `leakage`: derived year-level outcomes and chart-inference results.

The website reads these artifacts without changing them. The stored tables are the evidence for the displayed outcomes.
