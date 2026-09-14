# Administrator resolution workflow

This document describes what the scheduling software does with inputs it cannot schedule on its own, and what a responsible administrator must decide. The software never invents names, never drops an obligation silently, and never relaxes a hard constraint by itself.

## Scheduling outcomes

Every scheduling attempt ends in exactly one of four states:

| Outcome | Meaning | What to do |
|---|---|---|
| `scheduled` | every rotation released an independently validated chart | distribute the current chart with `sim/student_export.py` |
| `review_required` | pending submissions, screen returns, unresolved screening checks, rule violations without an approved exception, or an attendance conflict | resolve the items below and rerun |
| `proven_infeasible` | CP-SAT proved that no chart satisfies the hard constraints for some state | change an input: a list must change, an obligation must be waived, or capacities or staff constraints must change |
| `unknown` | bounded search found no valid chart and no validated fallback existed; this is not a proof of infeasibility | raise the feasibility budget, retry, or treat as `review_required` |

Within a scheduled year, each rotation carries a release status: `optimized` (the chart came from this rotation's search), `incumbent` (a validated cached chart was released because no search result beat it), or `fallback` (the search never produced a valid chart of its own, so the cached chart was released). All three are valid charts. A chart is marked as proven optimal only when CP-SAT returned OPTIMAL under the exact objective.

## Pending submissions

A nonempty list that fails the submission rule (fewer than four names, fewer than two same-grade names, or more than the cap) is stored as `pending_review`. Scheduling is blocked while any request is pending. Decisions, keyed by student:

- `approve`: keep the list as an approved exception; the student keeps the real obligation with the names given.
- `resubmit` with new names: the new list is classified again and must pass the rule, or it remains pending.
- `withdraw`: the student withdrew the request; recorded as voluntary nonsubmission after review, with the original names kept in the record.

In simulation, `--short-list-policy approve|withdraw` applies one of these decisions to every pending request and records that a policy, not a person, decided.

## Screen returns and unresolved checks

The pre-solve screens report, per eligibility state, proved-coercive candidate groups, capacity-demand shortfalls, unresolved candidates (no decision within the deterministic budget), and, for high-risk candidates, full-model separation results. A `forced` full-model verdict is a certificate that the group must share a table in every valid chart under the current constraints. An `unresolved` result is not a finding.

Returning lists to students is a policy decision. A forced group is not evidence of dishonest intent; it may be a sincere and concentrated friendship group. Options: ask the group to add names outside the group, accept the forced table, or adjust capacities. Record the decision and rerun.

## Attendance conflicts

For each rotation the active roster is the set of present students. A present student whose every listed companion is absent or ineligible is a conflict; the run stops and lists the student, the absent names, and the ineligible names. Decisions, per rotation and per student:

- waive the obligation for that rotation (`waivers={rotation: {student: reason}}`); the student is seated without the guarantee and the waiver is recorded in the trace;
- change attendance (the student or a companion is present after all);
- change the list through the review process.

In simulation, `--conflict-policy waive` records a waiver automatically and labels it as a simulation policy.

## Staff constraints

Prohibited pairs (two students who must not share a table) and placement restrictions (a student limited to certain tables) are hard constraints. They enter the feasibility check, the fallback cache key, the local search, CP-SAT, and the final validation. Supply them as JSON with student identifiers:

```json
{"prohibitedPairs": [["S001", "S002"]], "allowedTables": {"S010": [0, 1, 2, 3]}}
```

Explicit occupancy targets per table can also be supplied; they must respect physical capacities and seat exactly the present roster.

## Manual adjustments

Any manual change to a released chart must pass the same validation as a solver chart (`Problem.validate`), which checks unique placement, occupancy targets, eligibility, every present obligation, prohibited pairs, and placement restrictions. A chart that fails is not released. The validation report lists every violated constraint so the adjustment can be corrected.

## Records

Every run records: submission states and decisions, attendance and waivers, staff constraints, feasibility statuses per state, screening reports with coverage limits, the fallback cache summary, per-rotation release status and validation, and the full stage snapshots. These are staff records; see the data-handling policy.
