# Publication audit, 13 September 2026

The retained main-study results reproduce, but the manuscript received for review was not ready for submission. Its TeX described a newer implementation while its PDF, tables, and numerical macros still reflected an older study. It also presented an incomplete method comparison as a completed grid. This audit corrected the manuscript, rebuilt its evidence-derived assets, repaired confirmed implementation defects, and preserved the original experimental traces and source snapshots.

The current deliverables are [the revised TeX](../article/article.tex), [the rebuilt article PDF](../article/article.pdf), and [the implementation guide](methodology.pdf). The requested generative-AI acknowledgment was removed. The final source and extracted PDF text were checked for em dashes; bibliographic page-range en dashes are retained.

## Principal research and manuscript corrections

| Finding | Correction and effect |
|---|---|
| Historical numerical assets attached to revised prose | Regenerated all main-study macros, tables, and six figures from the verified revised manifests. The article now reports 618 forced list entries in the honest reference, rather than the stale 613, and 99.67% mean exactly-one coverage across honest populations. |
| Incomplete evaluation described as complete | Preserved the two original ledgers and assembled an explicitly partial evaluation. The text and captions disclose 48 attempts, 31 successful traces, and two nonterminal records. Only 44 unique method configurations were attempted from the planned grid of 72; 15 configurations have successful results for both methods. Outcome summaries are not presented as a balanced method-effect estimate. |
| Initial and replacement submissions mixed in screening table | Separated structural screening of the original attack from full-model tests of the replacement lists. Those full-model tests found zero forced groups, rather than supplying evidence of original-attack forcing. |
| Hardness theorem exceeded the stated list policy | Explicitly restricted the NP-completeness claim to the generalized model with unrestricted list lengths. The reduction does not prove hardness under the defended four-to-eight-name rule. |
| Absent and waived participants remained in mathematical obligations | Defined the present roster and active, unwaived obligation set; corrected guarantee, objective, CP sums, and structural hypotheses. |
| Random-meeting formula used physical capacities during absence | Replaced capacities with actual occupancy targets in pair probabilities, defined absent pairs to have zero probability, and clarified present eligible names and actual table occupancy in random coverage. The reference full-attendance numbers are unaffected. |
| Privacy exposure described as requiring no history | Explained that recurrence counts across observed rotations are necessary, even if full charts are not retained. Distinguished current-only logical forcing from history-based exposure. |
| Undisclosed exposure tie breaking | Stated ascending anonymous-ID tie breaking. There are 91 top-frequency ties in proposed charts and 153 in random charts; allowable tied choices give listed-peer rates of 93.4–98.8% and 1.6–12.5%, respectively. |
| Forcing, feasibility, and solver evidence conflated | Qualified forcing when base feasibility is UNKNOWN; distinguished solver INFEASIBLE from independent proof artifacts and direct empty-eligible-list contradictions. Stated that fixed-target infeasibility is not necessarily physical-room infeasibility. |
| Construction claimed to minimize the exact objective | Distinguished heuristic construction priorities from canonical scoring and subsequent optimization. Completed auxiliary-variable domains and nonnegative-weight assumptions. |
| Exploratory benchmark presented as fully traced evidence | Labeled the CP-formulation benchmark as summary-only, without retained returned assignments or source fingerprint. Its timings cannot receive the same independent validation as the primary study. |
| Public availability overstated | Confirmed that the public project and site exist, but the revised experiment manifest was unavailable at the public main-branch URL. The draft now states that the revised evidence and corrected source still require a versioned public release. |
| Bibliography and presentation | Verified cited works against primary sources, corrected Gelatt's name suffix, added missing DOIs, clarified several ambiguous sentences, repaired table widths, and removed the requested acknowledgment and em dashes. |

## Confirmed code defects repaired

- **Attendance and feasibility:** zero-present eligibility pools retained phantom occupied seats; explicit targets could likewise retain phantom seats. These are now rejected or closed appropriately. Empty-roster annealing returns a valid empty assignment. Feasibility preflight now checks actual requested rosters and eligibility states, rather than rejecting a schedule because a hypothetical full roster or unrequested state is infeasible. Attendance callbacks are evaluated once so provenance and execution use the same roster.
- **Fallback validation:** an assignment with invalid grade placement or occupancy could have zero scored search violations and displace a validated fallback. Pipeline guards now use independent full validity, not only the search penalty. The construction-and-repair comparator no longer invokes an optimizing emergency CP stage after its declared stopping point. A valid CP result identical to the cached chart is now attributed to the incumbent instead of incorrectly claiming the search found no valid chart.
- **Screening:** configured exact-enumeration and demand-closure budgets are now applied. Unresolved full-model checks block the review gate. Candidate indices are mapped correctly into compact present-roster models.
- **Privacy inference:** waived rotations no longer impose a companion hitting-set constraint. The independent CP verifier was corrected separately. Invalid retention windows and ranking counts are rejected.
- **Submission cap:** blanket or explicit exception approval could admit an over-cap list while observers were told a smaller public cap. Over-cap requests now remain pending or require resubmission/a cap change; short-list exceptions remain supported.
- **Synthetic generator:** a planted clique could exceed the declared nomination cap, including a negative-slice case producing extra names. Incompatible clique-size/cap settings now fail explicitly.
- **Student export:** removed the explicit absent-student roster from assignment-only exports. Missing names can still suggest absence; this is field minimization, not a confidentiality proof.
- **Paper build:** fixed a reused `counts` variable that caused `make_tables.py` to raise `KeyError: 'success'` after writing its outputs. Evaluation repeat costs now use the recorded integer objective scale instead of a hardcoded ten. Partial evaluation coverage remains explicit through the build.

These fixes are not retroactive edits to the experimental history. All retained successful traces identify the archived 11 September executable source. Current repairs are tested separately. No retained trace uses a waived obligation, an over-cap approved list, or an incompatible planted-clique cap; those repairs do not change the retained numbers.

## What the independent checks establish

The audit checked **63 successful traces covering 1,013 rotations**, comprising 2,026 proposed/random charts and their saved intermediate stages. The main study contains 32 traces and 517 rotations; the partial evaluation contains 31 traces and 496 rotations. Independent recomputation found **zero discrepancies** in chart validity, stage costs, recorded release outcomes, source/input identities, coalition results, contact counts, participant outcome summaries, coverage, and exposure.

| Quantity | Recomputed result |
|---|---:|
| Mean exactly-one rate over ten honest populations | 99.67% |
| Mean paired distinct-peer gain | 2.463813 |
| Population range of gains | 2.070039 to 2.988327 |
| Conditional 95% population-bootstrap interval | 2.274689 to 2.666148 |
| Honest reference mean contacts, proposed/random | 74.482490 / 72.311284 |
| Honest reference logically forced directed entries | 618 of 2,056 (30.1%) |

The bootstrap was recomputed from unrounded contact counts with the declared 20,000 resamples and seed. Independent mathematical enumeration checked small circulants, shared-anchor partitions, omission-star patterns, and the attendance-adjusted probability counterexample. The original suite passed 264 tests with one skipped before repairs. The full paper build passed, including reassembly, independent chart checks, all 32 main-study privacy checks, figure generation, and both PDFs. The final article contains 24 pages with zero LaTeX warnings or em-dash occurrences; the site-download PDF matches it byte for byte. The final full suite passed **292 tests, with one skipped**, in 57.86 seconds. The one skip is an intentional excluded circulant parameter combination (`n=k=4`), not a missing dependency. Commands: `.venv/bin/python -m pytest -q` and `bash paper/build.sh`.

This establishes consistency of the available artifacts, not that every possible input or attack has been exhausted. No full study was rerun under the repaired executable source, and no empirical result was invented to fill missing evaluation cells.

## Remaining research and submission work

1. **Evaluation coverage remains incomplete.** Most stress conditions have only one successful population pair. Complete the planned runs before making a three-population claim for every condition, or retain the explicit partial-study scope. The two nonterminal historical records are not assumed to be failures or successes.
2. **Screening coverage is bounded.** Structural admission screening uses the full submitted roster in requested eligibility states and can conservatively request review despite an attendance-specific solution. Full-model tests use the first actual roster in each state; later changed rosters receive feasibility checks, not new coalition-separation searches. Larger, multiple-anchor, and adaptive attacks remain outside exhaustive coverage.
3. **Occupancy targets are a design choice.** Largest-first reduction can create singleton targets even if a different allocation of the same physical seats admits a valid chart. Existing infeasibility statements are about the supplied targets and other hard constraints.
4. **Benchmark evidence is incomplete.** A rigorous formulation-performance comparison needs retained returned charts, source/input identities, controlled hardware conditions, and a reproducible rerun. The existing summary is explicitly exploratory.
5. **External validity is limited.** No real-school intervention, measured wellbeing outcome, calibrated network, comparison with a documented school procedure, full-year optimum, or extensive ablation study is supplied. Synthetic contact counts do not establish student benefit or fairness.
6. **Author declarations remain unfinished.** The full institution represented by SMU, confirmed affiliations/contributions, funding, and competing interests require author-provided facts. No target journal was supplied, so journal-specific requirements have not been verified. Existing placeholders were not replaced with invented declarations.
7. **Record the submission version.** This repository update includes the corrected manuscript, code, retained evidence, and source snapshots. Record the exact commit or tagged release used for journal submission. No journal submission was performed during this audit.

## Detailed audit trail

The pre-audit working files, initial Git status/diff, source hashes, independent scripts, JSON evidence, and logs are preserved in the local archive `audit/review_2026-09-13/`, outside this repository. That archive includes mathematics/reference, empirical/privacy, solver/screening, recomputation, enumeration, and public-availability reports. Existing user edits were retained; the initial checkout was already substantially modified.

The public repository contains these verification records and the source needed to inspect them:

- [Revised study chart checks](../results/verification/revised_charts.json)
- [Evaluation chart checks](../results/verification/revised_evaluation_charts.json)
- [Privacy verification](../results/verification/revised_privacy.json)
- [Archived executable source](../results/source_snapshots/e1a4d21af6c3e2c42dc8ad8d448005a79abe393a0927d466e591b24f7f9561bb/README.txt)
- [Verification instructions](../results/verification/README.md)
