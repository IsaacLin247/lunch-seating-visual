"""Scenario definitions, the full-year runner, trace assembly and validation.

Scheduling outcomes are explicit and never conflated:

  scheduled          every rotation released an independently validated chart
                     (per rotation: ``optimized`` or ``fallback``; optimality is
                     asserted only with a CP-SAT proof under the exact objective)
  review_required    pending submissions, screen returns, unresolved checks,
                     invalid lists or attendance conflicts need a decision
  proven_infeasible  CP-SAT proved that the hard constraints admit no chart
  unknown            bounded search found no valid chart and no validated
                     fallback existed; this is not a proof of infeasibility
"""
from __future__ import annotations

import inspect
import random
import time
from datetime import datetime, timezone

import numpy as np

from .attendance import RotationRoster, sample_absences
from .baseline import expected_distinct, expected_friend_coverage
from .constraints import SchedulingConflict, StaffConstraints, hard_constraint_key, validate_chart
from .diagnostics import recurring_group_report
from .fallbacks import FeasibleChartCache
from .generator import (Network, make_cohort, honest_lists, coalition_lists, student_id, submission_report)
from .metrics import individual_outcomes, participation_summary
from .objective import objective_from_config
from .privacy import coseating_exposure, leakage_report, windowed_leakage
from .provenance import source_provenance, trace_provenance
from .screens import ScreenBudget, full_model_screen, run_screens
from .solver import (Problem, table_layout, solve_rotation, random_assignment, feasibility_certificate,
                     InfeasibleInputError, SolveFailed, VIOL, W_EXTRA, W_M, W_ALPHA, SCALE, T0, T1,
                     W_2PLUS_CPSAT, CPSAT_REPEAT_SCALE)
from .submissions import SubmissionRules, build_submissions, obligation_lists, summarize as summarize_submissions

ROTATIONS = 16
STATES = ("mixed", "same")
METHODS = ("hybrid", "construct_repair")
CONFLICT_POLICIES = ("stop", "waive")

SCENARIOS = {
    "honest": {
        "title": "The whole room",
        "short": "Honest lists",
        "description": "Every student submits their true friends. Random status quo vs. the proposed system.",
        "coalitionMode": None,
        "rules": {"min4": True, "screens": True},
    },
    "coalition_none": {
        "title": "Gaming it: no defenses",
        "short": "No defenses",
        "description": "Six students each list only the next member of their group (k=1 chain). No submission rules, no screens.",
        "coalitionMode": "k1",
        "rules": {"min4": False, "screens": False},
    },
    "coalition_min4": {
        "title": "Gaming it: min-4 rule",
        "short": "Min-4 rule",
        "description": "Six members use the omission star: its structural mean cluster is at least three. Feasible patterns include 3+3, 4+2 and all six; the displayed pattern is measured from each chart. Screens off.",
        "coalitionMode": "min4",
        "rules": {"min4": True, "screens": False},
    },
    "coalition_stratified": {
        "title": "Gaming it: hiding behind the other grade",
        "short": "Same-grade attack",
        "description": "Five members list the next two around a cycle plus two seniors each, the sixth lists four of the five. In same-grade rotations the seniors vanish from the effective lists and all six are forced onto one table. Min-4 rule on, screens off.",
        "coalitionMode": "stratified",
        "rules": {"min4": True, "screens": False},
    },
    "coalition_screened": {
        "title": "Gaming it: screens on",
        "short": "Screens on",
        "description": "The six-member same-grade attack is returned by the screen. The experiment then supplies an omission-star resubmission, the strongest structural bound within the purely internal four-of-five family, and validates it before seating.",
        "coalitionMode": "screened",
        "rules": {"min4": True, "screens": True},
    },
    "coalition_shared_anchor": {
        "title": "Gaming it: one shared outside anchor",
        "short": "Shared-anchor attack",
        "description": "Seven juniors name their cycle successor, one common outside junior and two seniors. They force a full table in same-grade rounds. Enforcement is disabled to display the attack; the diagnostic reports what the revised screen proves.",
        "coalitionMode": "shared_anchor",
        "rules": {"min4": True, "screens": False},
    },
}
SCENARIOS["infeasible_demand"] = {
    "title": "Known infeasible input",
    "short": "Infeasible demand",
    "description": "Five mutual core members plus ten followers who list only the core: every table touching them needs two core members, so fifteen students cannot be seated at two tables. CP-SAT proves infeasibility; nothing is scheduled. Screens off so the certificate, not the screen, decides.",
    "coalitionMode": "demand_core",
    "rules": {"min4": True, "screens": False},
}
SCENARIOS = {name: SCENARIOS[name] for name in (
    "honest", "coalition_none", "coalition_min4", "coalition_stratified",
    "coalition_shared_anchor", "coalition_screened", "infeasible_demand")}
WEBSITE_SCENARIOS = ("honest", "coalition_none", "coalition_min4", "coalition_stratified",
                     "coalition_shared_anchor", "coalition_screened")


class SubmissionReviewRequired(ValueError):
    """Approved input is required before a screen-enabled year can be seated."""

    def __init__(self, message, review=None):
        super().__init__(message)
        self.review = review or {}


def coalition_members(net: Network, scenario: str):
    members = list(net.clique)
    if SCENARIOS[scenario]["coalitionMode"] == "shared_anchor":
        members.append(next(i for i in range(net.n11) if i not in members))
    return members


def shared_anchor_lists(net: Network, base):
    members = coalition_members(net, "coalition_shared_anchor")
    outside = next(i for i in range(net.n11) if i not in members)
    seniors = [i for i in range(net.n) if net.grade[i] != net.grade[members[0]]][:2]
    if len(seniors) != 2:
        raise ValueError("the shared-anchor example needs two other-grade students")
    out = [list(l) for l in base]
    for k, i in enumerate(members):
        out[i] = [members[(k + 1) % len(members)], outside, *seniors]
    return out


def demand_core_lists(net: Network, base):
    """Five mutual junior core members and ten junior followers listing only the core.

    The demand bound (Proposition on demand) shows at most two tables can hold
    these fifteen students, so the instance is infeasible in every state.
    """
    juniors = [i for i in range(net.n11) if i not in net.clique]
    core = juniors[:5]
    followers = juniors[5:15]
    out = [list(l) for l in base]
    for i in core:
        out[i] = [j for j in core if j != i]
    for i in followers:
        out[i] = core[:4]
    return out


def pick_hero(net: Network) -> int:
    """A mid-popularity junior who is not in the planted clique."""
    juniors = [i for i in range(net.n11) if i not in net.clique]
    juniors.sort(key=lambda i: net.popularity[i])
    return juniors[len(juniors) // 2]


def state_for(rot_idx: int, first_state: str = "mixed") -> str:
    k = STATES.index(first_state)
    return STATES[(k + rot_idx) % 2]


def _caps_by_state(net: Network):
    caps_m, _ = table_layout("mixed", net.n11, net.n12)
    caps_s, tg = table_layout("same", net.n11, net.n12)
    return {"mixed": caps_m, "same": caps_s}, {g: [c for c, t in zip(caps_s, tg) if t == g] for g in (11, 12)}


def scenario_rules(scenario: str) -> SubmissionRules:
    return SubmissionRules.from_scenario(SCENARIOS[scenario]["rules"])


def build_lists(net: Network, scenario: str, short_list_policy: str = "review", nonsubmit_frac: float = 0.0,
                list_cap: int | None = None, review_decisions=None, screen_budget=None):
    """Return (lists_used, extra) where extra carries submissions, the screen report etc.

    Raw lists are classified into explicit submission states; ``lists_used``
    are the resulting obligations.  Nothing is invented or silently dropped.
    """
    spec = SCENARIOS[scenario]
    mode = spec["coalitionMode"]
    rules = scenario_rules(scenario)
    grade = [int(g) for g in net.grade]
    extra = {}
    raw = honest_lists(net, nonsubmit_frac=nonsubmit_frac, short_list_policy=short_list_policy, list_cap=list_cap)
    caps_by_state, _ = _caps_by_state(net)

    def classify(raw_lists):
        subs = build_submissions(raw_lists, grade, rules, short_list_policy, review_decisions)
        return subs, obligation_lists(subs)

    if mode is None:
        submissions, lists = classify(raw)
        if spec["rules"]["screens"]:
            extra["screen"] = _screen_report(lists, net, caps_by_state, flagged_expected=False, budget=screen_budget)
    elif mode in ("k1", "min4", "stratified"):
        submissions, lists = classify(coalition_lists(net, mode, raw))
    elif mode == "demand_core":
        submissions, lists = classify(demand_core_lists(net, raw))
    elif mode == "shared_anchor":
        submissions, lists = classify(shared_anchor_lists(net, raw))
        extra["diagnosticScreen"] = _screen_report(
            lists, net, caps_by_state, flagged_expected=True,
            coalition=coalition_members(net, scenario), budget=screen_budget)
    elif mode == "screened":
        _, first = classify(coalition_lists(net, "stratified", raw))
        rep = _screen_report(first, net, caps_by_state, flagged_expected=True, budget=screen_budget)
        extra["screen"] = rep
        extra["listedInitial"] = first
        # A specified adversarial response within the internal four-of-five family.
        submissions, lists = classify(coalition_lists(net, "min4", raw))
        rep["resubmission"] = "adversarial: strongest passing 4-of-5 wiring (omission star)"
        rep["afterResubmission"] = _screen_report(lists, net, caps_by_state, flagged_expected=False, budget=screen_budget)
    else:
        raise ValueError(mode)
    extra["submissions"] = submissions
    extra["rules"] = rules
    return lists, extra


def _ids(seq):
    return [student_id(m) for m in seq]


def _screen_report(lists, net: Network, caps_by_state, flagged_expected: bool, coalition=None, budget=None, states=None):
    _, grade_caps = _caps_by_state(net)
    r = run_screens(lists, list(int(g) for g in net.grade), caps_by_state,
                    caps_by_grade_by_state={"same": grade_caps}, budget=budget, states=states)
    coalition = set(net.clique if coalition is None else coalition)
    returned = set(r["returnedStudents"])
    per_state = {}
    for state, ps in r["perState"].items():
        per_state[state] = {
            "candidates": [_screen_ids(c) for c in ps["candidates"]],
            "flags": [_screen_ids(f) for f in ps["flags"]],
            "demandFlags": [_screen_ids(f) for f in ps["demandFlags"]],
            "unresolvedCandidates": [_screen_ids(c) for c in ps.get("unresolvedCandidates", [])],
            "coverage": ps.get("coverage", {}),
            "demandStatus": ps.get("demandStatus"),
            "ineligible": _ids(ps["ineligible"]),
        }
    return {
        "rule": r["rule"],
        "states": r["states"],
        "perState": per_state,
        "rawPerState": r["perState"],          # index form, consumed by the full-model screen
        "flaggedStudents": _ids(r["flaggedStudents"]),
        "returnedStudents": _ids(r["returnedStudents"]),
        "min4Violations": _ids(r["min4Violations"]),
        "sameGradeViolations": _ids(r["sameGradeViolations"]),
        "nFlagged": len(r["flaggedStudents"]),
        "nReturned": len(returned),
        "unresolvedCandidates": [_screen_ids(c) for c in r.get("unresolvedCandidates", [])],
        "nUnresolved": len(r.get("unresolvedCandidates", [])),
        "unresolvedChecks": r.get("unresolvedChecks", []),
        "ineligible": _ids(r["ineligible"]),
        "budget": r.get("budget"),
        "coalitionFlagged": (bool(set(r["flaggedStudents"]) & coalition) and coalition <= returned)
        if flagged_expected else None,
        "honestFlagged": _ids(sorted(m for m in returned if m not in coalition)),
    }


def _screen_ids(record):
    out = dict(record)
    for key in ("members", "submitters", "seeds", "core", "followers", "externalAnchors", "outsideAnchors", "boundary",
                "outside", "relaxationMembers", "anchorDeletions"):
        if key in out:
            out[key] = _ids(out[key])
    if "split" in out:
        out["split"] = [_ids(part) for part in out["split"]]
    return out


def _full_model_ids(report, ids):
    out = {k: v for k, v in report.items() if k != "results"}
    out["results"] = []
    for r in report["results"]:
        rec = {k: v for k, v in r.items() if k != "witness"}
        rec["group"] = [ids[m] for m in r["group"]]
        if "witness" in r:
            rec["witnessTables"] = r.get("witnessTables")
        out["results"].append(rec)
    return out


def _anchor_for(i, table_members, adj, history_total):
    peers = [j for j in table_members if j in adj]
    if not peers:
        return None
    peers.sort(key=lambda j: (history_total[i][j], j))
    return peers[0]


def _pct(num, den):
    return round(100.0 * num / den, 2) if den else 0.0


def _versions():
    p = source_provenance()
    return {**p["versions"], "gitCommit": p["gitCommit"], "gitDirty": p["gitDirty"],
            "effectiveSourceHash": p["effectiveSourceHash"]}


def _quantiles(values):
    v = sorted(values)
    q = lambda f: float(v[min(len(v) - 1, int(round(f * (len(v) - 1))))])  # noqa: E731
    return {"min": v[0], "q1": q(0.25), "median": q(0.5), "q3": q(0.75), "max": v[-1], "mean": round(sum(v) / len(v), 2)}


def _review_gate(scenario, review, submissions_summary, rules_min4):
    """Everything that must be decided before a screen-enabled year is seated."""
    reasons = []
    if submissions_summary["pendingReview"]:
        reasons.append(f"{len(submissions_summary['pendingReview'])} submission(s) pending review")
    for key in ("returnedStudents", "unresolvedCandidates", "unresolvedChecks", "ineligible"):
        if review.get(key):
            reasons.append(f"{key}={len(review[key])}")
    if rules_min4:
        approved = set(submissions_summary["approvedExceptions"])
        offenders = [s for s in review.get("min4Violations", []) + review.get("sameGradeViolations", []) if s not in approved]
        if offenders:
            reasons.append(f"{len(set(offenders))} list(s) fail the submission rule without an approved exception")
    forced = [r for r in (review.get("fullModelScreen") or {}).get("forcedGroups", [])]
    if forced:
        reasons.append(f"{len(forced)} group(s) forced together under the full model")
    unresolved = (review.get("fullModelScreen") or {}).get("unresolvedGroups", [])
    if unresolved:
        reasons.append(f"{len(unresolved)} unresolved full-model separation check(s)")
    return reasons


def run_year(net: Network, lists, scenario: str, seed: int = 7, first_state: str = "mixed",
             anneal_iters: int = 300_000, cpsat_time: float = 3.5, workers: int = 8,
             deterministic: bool = True, feasibility_time: float = 20.0, log=print,
             rotations: int = ROTATIONS, generator_config=None, *, submissions=None, short_list_policy="review",
             method: str = "hybrid", objective=None, cpsat_pairs: str = "all", cpsat_extras: str = "count",
             attendance=None, absence_rate: float = 0.0, conflict_policy: str = "stop", waivers=None,
             staff=None, screen_budget=None, suspected_groups=None, review_decisions=None) -> dict:
    spec = SCENARIOS[scenario]
    if rotations < 1:
        raise ValueError("rotations must be positive")
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}")
    if conflict_policy not in CONFLICT_POLICIES:
        raise ValueError(f"unknown conflict policy {conflict_policy!r}")
    n = net.n
    if len(lists) != n or any(len(l) != len(set(l)) or i in l or
                             any(not isinstance(j, (int, np.integer)) or not 0 <= j < n for j in l)
                             for i, l in enumerate(lists)):
        raise ValueError("submitted lists must have distinct, valid, non-self student indices")
    grade = [int(g) for g in net.grade]
    ids = net.ids()
    obj = objective_from_config(objective)
    staff = staff if isinstance(staff, StaffConstraints) else StaffConstraints.from_dict(staff, ids)
    budget = ScreenBudget.from_dict(screen_budget)
    rules = scenario_rules(scenario)
    if submissions is None:
        submissions = build_submissions(lists, grade, rules, short_list_policy, review_decisions)
        lists = obligation_lists(submissions)
    sub_summary = summarize_submissions(submissions, ids)
    hist_m = [[0] * n for _ in range(n)]        # incidental co-seatings (pair not listed at the time)
    hist_a = [[0] * n for _ in range(n)]        # listed-pair co-seatings
    hist_total = [[0] * n for _ in range(n)]
    hist_rand = [[0] * n for _ in range(n)]
    listed = [set(l) for l in lists]
    for i in range(n):
        for j in lists[i]:
            listed[j].add(i)
    prev = None
    rotation_records = []
    clique = coalition_members(net, scenario)
    caps_by_state, caps_same_by_grade = _caps_by_state(net)
    waivers = {int(k): v for k, v in (waivers or {}).items()}   # rotation index (0-based) -> {student: reason}
    # Materialize attendance once, so the roster used by the solver is exactly
    # the roster recorded in provenance even for a stateful attendance callback.
    attendance_by_rotation = None if attendance is None else {
        r: list(attendance(r) if callable(attendance) else attendance.get(r, attendance.get(str(r), [])))
        for r in range(rotations)}
    rosters = []
    for r in range(rotations):
        state = state_for(r, first_state)
        caps, tg = table_layout(state, net.n11, net.n12)
        absent = (attendance_by_rotation[r] if attendance_by_rotation is not None else
                  sample_absences(n, absence_rate, seed, r))
        rot_waivers = dict(waivers.get(r, {}))
        roster = RotationRoster(grade, lists, caps, tg, state, absent=absent, waivers=rot_waivers, staff=staff)
        if roster.conflicts:
            if conflict_policy == "waive":
                for c in roster.conflicts:
                    rot_waivers[c["student"]] = "simulation policy: obligation waived for this rotation (no present eligible companion)"
                roster = RotationRoster(grade, lists, caps, tg, state, absent=absent, waivers=rot_waivers, staff=staff)
            else:
                raise SchedulingConflict(
                    f"{scenario} rotation {r + 1}: {len(roster.conflicts)} present student(s) have no present eligible listed "
                    f"companion; an administrator must resolve this before seating", roster.describe(ids)["conflicts"])
        rosters.append(roster)
    planned_states = list(dict.fromkeys(roster.state for roster in rosters))

    def roster_key(roster):
        return hard_constraint_key(grade, [[] if i in roster.waivers else lists[i] for i in range(n)],
                                   roster.caps, roster.table_grade, roster.state, present=roster.present,
                                   staff=staff, targets=roster.targets)

    run_config = run_config_dict(scenario, seed, first_state=first_state, rotations=rotations,
                                 anneal_iters=anneal_iters, cpsat_time=cpsat_time, workers=workers,
                                 deterministic=deterministic, feasibility_time=feasibility_time, method=method,
                                 extra_weight=float(obj.extra_weight), cpsat_pairs=cpsat_pairs,
                                 cpsat_extras=cpsat_extras, absence_rate=absence_rate, conflict_policy=conflict_policy)
    extra_inputs = {}
    if not staff.is_empty():
        extra_inputs["staffConstraints"] = staff.to_dict(ids)
    if attendance is not None:
        extra_inputs["attendance"] = {str(r): sorted(ids[i] for i in attendance_by_rotation[r]) for r in range(rotations)}
    if waivers:
        extra_inputs["waivers"] = {str(r): {ids[i]: reason for i, reason in w.items()} for r, w in waivers.items()}
    if objective is not None and obj.describe() != objective_from_config(None).describe():
        extra_inputs["objective"] = obj.describe()
    provenance = trace_provenance(net, lists, run_config, generator_config, extra_inputs=extra_inputs or None)

    # ----- admission review gate ---------------------------------------------
    review = None
    if spec["rules"]["screens"]:
        review = _screen_report(lists, net, caps_by_state, flagged_expected=False, coalition=clique, budget=budget,
                                states=planned_states)

    # ----- pre-solve feasibility certificates and validated fallbacks --------
    cache = FeasibleChartCache()
    feas = {}
    full_model = {}
    for state in planned_states:
        roster = next(rr for rr in rosters if rr.state == state)
        p0 = Problem(roster.grade, roster.lists, roster.caps, roster.table_grade, roster.restrict_matrix(hist_m), state,
                     history_alpha=roster.restrict_matrix(hist_a), objective=obj, staff=roster.staff, targets=roster.targets)
        key = roster_key(roster)
        t0 = time.perf_counter()
        witness = None
        try:
            status, witness = feasibility_certificate(p0, time_limit=feasibility_time, workers=workers, seed=seed,
                                                      deterministic=deterministic)
        except InfeasibleInputError as e:
            status = f"INFEASIBLE_INPUT: {e}"
        if witness is not None:
            cache.store(key, p0, witness, source=f"feasibility-certificate:{state}")
        feas[state] = {"status": status, "seconds": round(time.perf_counter() - t0, 2), "key": key,
                       "witnessCached": witness is not None}
        if log:
            log(f"  [{scenario}] feasibility ({state}): {status} in {feas[state]['seconds']}s")
        if status.startswith("INFEASIBLE"):
            raise InfeasibleInputError(f"{scenario}: the submitted lists admit no seating in {state} rotations ({status})")
        # full-model separation tests on high-risk screened candidates
        source_report = review if review is not None else None
        if source_report is not None or suspected_groups:
            per_state = (source_report or {}).get("rawPerState", {}).get(state, {"candidates": []})
            # Screen candidates use full-roster indices; the actual assignment
            # model uses compact indices of present students.
            per_state = {**per_state, "candidates": [
                {**c, **{field: [roster.index[i] for i in c[field] if i in roster.index]
                          for field in ("core", "submitters", "members") if field in c}}
                for c in per_state.get("candidates", [])]}
            active_groups = [[roster.index[i] for i in group if i in roster.index] for group in suspected_groups or []]
            fm = full_model_screen(p0, per_state, budget=budget, seed=seed, deterministic=deterministic,
                                   base_status=status, groups=active_groups)
            full_model[state] = {**_full_model_ids(fm, [ids[i] for i in roster.present]),
                                 "hardConstraintKey": key,
                                 "scope": "first requested roster in this eligibility state"}
    if review is not None:
        review["fullModelScreen"] = {
            "perState": full_model,
            "forcedGroups": [dict(r, state=s) for s, rep in full_model.items() for r in rep["results"] if r["verdict"] == "forced"],
            "unresolvedGroups": [dict(r, state=s) for s, rep in full_model.items() for r in rep["results"] if r["verdict"] == "unresolved"],
        }
        reasons = _review_gate(scenario, review, sub_summary, spec["rules"]["min4"])
        if reasons:
            raise SubmissionReviewRequired(
                f"{scenario}: submissions need review before seating ({'; '.join(reasons)})", review)
    elif sub_summary["pendingReview"]:
        raise SubmissionReviewRequired(
            f"{scenario}: {len(sub_summary['pendingReview'])} submission(s) pending review", {"submissions": sub_summary})

    t_year = time.perf_counter()
    for r in range(rotations):
        roster = rosters[r]
        state, caps, tg = roster.state, roster.caps, roster.table_grade
        rot_waivers = roster.waivers
        p = Problem(roster.grade, roster.lists, caps, tg, roster.restrict_matrix(hist_m), state,
                    prev_tables=roster.restrict_tables(prev), history_alpha=roster.restrict_matrix(hist_a),
                    objective=obj, staff=roster.staff, targets=roster.targets)
        key = roster_key(roster)
        rot_feas = feas[state]["status"] if key == feas[state]["key"] else None
        if rot_feas is None:
            # new hard constraints (absences, waivers): certify and cache a chart for this key
            t0 = time.perf_counter()
            try:
                rot_feas, witness = feasibility_certificate(p, time_limit=feasibility_time, workers=workers,
                                                            seed=seed * 1000 + r, deterministic=deterministic)
            except InfeasibleInputError as e:
                rot_feas, witness = f"INFEASIBLE_INPUT: {e}", None
            if witness is not None:
                cache.store(key, p, witness, source=f"feasibility-certificate:rotation-{r + 1}")
            if rot_feas.startswith("INFEASIBLE"):
                raise InfeasibleInputError(f"{scenario} rotation {r + 1}: no valid chart exists for the present roster ({rot_feas})")
            feas_seconds = round(time.perf_counter() - t0, 2)
        else:
            feas_seconds = 0.0
        fallbacks = cache.charts(key, p)
        assign, info = solve_rotation(p, seed=seed * 1000 + r, anneal_iters=anneal_iters,
                                      cpsat_time=cpsat_time, workers=workers, deterministic=deterministic,
                                      fallbacks=fallbacks, cpsat_pairs=cpsat_pairs, cpsat_extras=cpsat_extras,
                                      method=method)
        release = validate_chart(p, assign)
        assert release["valid"], f"{scenario} rotation {r+1}: released chart failed validation: {release['problems'][:3]}"
        cache.store(key, p, assign, source=f"released:rotation-{r + 1}")
        members_c = p.members_of(assign)
        members = [[roster.present[i] for i in m] for m in members_c]   # roster indices

        rng_r = random.Random(f"{seed}-random-{r}")
        rassign = random_assignment(p, rng_r)
        rmembers_c = p.members_of(rassign)
        rmembers = [[roster.present[i] for i in m] for m in rmembers_c]
        for t in range(p.T):
            assert len(rmembers[t]) == roster.targets[t]

        present_set = set(roster.present)
        obligated = [i for i in roster.present if lists[i] and i not in rot_waivers]
        adj_full = {i: {j for j in lists[i] if (state == "mixed" or grade[j] == grade[i]) and j in present_set}
                    for i in obligated}
        cnt = {i: sum(1 for j in members[assign[roster.index[i]]] if j in adj_full[i]) for i in obligated}
        rcnt = {i: sum(1 for j in rmembers[rassign[roster.index[i]]] if j in adj_full[i]) for i in obligated}
        anchors, ranchors = {}, {}
        for i in obligated:
            a = _anchor_for(i, members[assign[roster.index[i]]], adj_full[i], hist_total)
            if a is not None:
                anchors[ids[i]] = ids[a]
            ra = _anchor_for(i, rmembers[rassign[roster.index[i]]], adj_full[i], hist_rand)
            if ra is not None:
                ranchors[ids[i]] = ids[ra]

        def n_repeats(ms, h):
            k = 0
            for m in ms:
                for x in range(len(m)):
                    for y in range(x + 1, len(m)):
                        if h[m[x]][m[y]] > 0:
                            k += 1
            return k
        rep = n_repeats(members, hist_total)
        rrep = n_repeats(rmembers, hist_rand)
        for m in members:
            for x in m:
                for y in m:
                    if x != y:
                        hist_total[x][y] += 1
                        if y in listed[x]:
                            hist_a[x][y] += 1
                        else:
                            hist_m[x][y] += 1
        for m in rmembers:
            for x in m:
                for y in m:
                    if x != y:
                        hist_rand[x][y] += 1
        met = np.mean([sum(1 for b in range(n) if hist_total[a][b] > 0) for a in range(n)])
        rmet = np.mean([sum(1 for b in range(n) if hist_rand[a][b] > 0) for a in range(n)])

        ns = len(obligated)
        cp = info.get("cpsat") or {}
        stats = {
            "pctGe1": _pct(sum(1 for i in obligated if cnt[i] >= 1), ns),
            "pctExactly1": _pct(sum(1 for i in obligated if cnt[i] == 1), ns),
            "pctGe2": _pct(sum(1 for i in obligated if cnt[i] >= 2), ns),
            "pctGe1Random": _pct(sum(1 for i in obligated if rcnt[i] >= 1), ns),
            "pctExactly1Random": _pct(sum(1 for i in obligated if rcnt[i] == 1), ns),
            "pctGe2Random": _pct(sum(1 for i in obligated if rcnt[i] >= 2), ns),
            "obligatedPresent": ns,
            "present": len(roster.present),
            "absent": len(roster.absent),
            "meanDistinctMet": round(float(met), 2),
            "meanDistinctMetRandom": round(float(rmet), 2),
            "repeatPairs": rep,
            "repeatPairsRandom": rrep,
            "cost": info["final"],
            "acceptedPhase": info["accepted"],
            "status": info["status"],
            "optimalityProven": info.get("optimalityProven", False),
            "cpsatStatus": cp.get("status"),
            "cpsatExact": cp.get("exact"),
            "cpsatObjective": cp.get("objective"),
            "cpsatBound": cp.get("bound"),
            "cpsatPairVariables": cp.get("pairVariables"),
            "cpsatConstraints": cp.get("constraints"),
            "cpsatObjectiveGap": cp.get("objectiveGap"),
            "solveTime": round(info["time"]["total"], 2),
            "fallbackTime": round(info["time"]["fallback"], 2),
            "feasibilityTime": feas_seconds,
            "annealRetries": info.get("annealRetries", 0),
            "fallbacksConsidered": len(info["fallbacks"]["considered"]),
            "fallbacksValid": sum(1 for c in info["fallbacks"]["considered"] if c["valid"]),
        }
        rot = {
            "idx": r + 1,
            "state": state,
            "tables": [[ids[i] for i in m] for m in members],
            "tablesRandom": [[ids[i] for i in m] for m in rmembers],
            "targets": roster.targets,
            "absent": [ids[i] for i in roster.absent],
            "waivedObligations": {ids[i]: reason for i, reason in sorted(rot_waivers.items())},
            "anchors": anchors,
            "anchorsRandom": ranchors,
            "stats": stats,
            "release": {"status": info["status"], "accepted": info["accepted"],
                        "optimalityProven": info.get("optimalityProven", False),
                        "feasibilityStatus": rot_feas, "hardConstraintKey": key,
                        "validation": info["validation"], "fallbacks": info["fallbacks"]},
            "pipeline": [{"name": name, "tables": [[ids[roster.present[i]] for i in m] for m in p.members_of(info["snapshots"][key_])],
                          "cost": info[key_], "seconds": round(info["time"][time_key], 4)}
                         for name, key_, time_key in (("construction", "greedy", "greedy"),
                                                     ("repair", "repair", "repair"),
                                                     ("annealing", "anneal", "anneal"),
                                                     ("final", "final", "cpsat"))],
        }
        rot["pipeline"][-1]["seconds"] = round(info["time"]["cpsat"] + info["time"]["fallback"], 4)
        if spec["coalitionMode"] is not None:
            full_assign = roster.expand(assign)
            full_rassign = roster.expand(rassign)
            rot["coalition"] = _coalition_stats(clique, full_assign, ids)
            rot["coalitionRandom"] = _coalition_stats(clique, full_rassign, ids)
        rotation_records.append(rot)
        prev = members
        if log:
            c = rot.get("coalition")
            log(f"  [{scenario}] rotation {r+1:2d} {state:5s} ge1={stats['pctGe1']:5.1f}% "
                f"exactly1={stats['pctExactly1']:5.1f}% met={stats['meanDistinctMet']:5.1f} "
                f"(rand {stats['meanDistinctMetRandom']:5.1f}) cost={info['final']['total']:5d} "
                f"{info['accepted']:6s} {stats['solveTime']:5.1f}s"
                + (f" coalition {c['pattern']} mean={c['avgCluster']}" if c else ""))
    year_time = time.perf_counter() - t_year

    # per-student outcome distribution (fairness tails)
    distinct = [sum(1 for b in range(n) if hist_total[a][b] > 0) for a in range(n)]
    in_deg = [0] * n
    for i in range(n):
        for j in lists[i]:
            in_deg[j] += 1
    order = sorted(range(n), key=lambda i: (in_deg[i], i))
    q = len(order) // 4
    fairness = {
        "distinctMet": _quantiles(distinct),
        "lowestInDegreeQuartile": {"n": q, "meanInDegree": round(sum(in_deg[i] for i in order[:q]) / q, 2),
                                   "meanDistinctMet": round(sum(distinct[i] for i in order[:q]) / q, 2)},
        "highestInDegreeQuartile": {"n": q, "meanInDegree": round(sum(in_deg[i] for i in order[-q:]) / q, 2),
                                    "meanDistinctMet": round(sum(distinct[i] for i in order[-q:]) / q, 2)},
    }
    states = [state_for(r, first_state) for r in range(rotations)]
    baseline = {
        "expectedDistinctRandom": round(expected_distinct(grade, caps_by_state["mixed"], caps_same_by_grade, states), 3),
        "expectedDistinctRandomAllMixed": round(expected_distinct(grade, caps_by_state["mixed"], caps_same_by_grade,
                                                                  ["mixed"] * rotations), 3),
        "expectedFriendCoverageMixed": round(expected_friend_coverage(grade, lists, caps_by_state["mixed"], caps_same_by_grade, "mixed"), 3),
        "expectedFriendCoverageSame": round(expected_friend_coverage(grade, lists, caps_by_state["mixed"], caps_same_by_grade, "same"), 3),
        "note": "Closed-form expectations assume the full roster; with absences the simulated random charts are the comparator.",
    }
    baseline["expectedFriendCoverageSchedule"] = round(
        (baseline["expectedFriendCoverageMixed"] * states.count("mixed") + baseline["expectedFriendCoverageSame"] * states.count("same")) / rotations, 3)

    lists_by_id = {ids[i]: {ids[j] for j in lists[i]} for i in range(n)}
    grade_by_id = {ids[i]: grade[i] for i in range(n)}
    outcomes = {
        "proposed": individual_outcomes(rotation_records, ids, lists_by_id, grade_by_id, key="tables"),
        "random": individual_outcomes(rotation_records, ids, lists_by_id, grade_by_id, key="tablesRandom"),
        "participation": participation_summary(rotation_records, ids, sub_summary),
    }
    recurring = {"proposed": recurring_group_report(rotation_records, key="tables"),
                 "random": recurring_group_report(rotation_records, key="tablesRandom")}

    trace = {
        "config": {
            "scenario": scenario,
            "title": spec["title"],
            "short": spec["short"],
            "description": spec["description"],
            "seed": seed,
            "n": n, "n11": net.n11, "n12": net.n12, "K": net.K,
            "rotations": rotations,
            "firstState": first_state,
            "tableCapacities": caps_by_state["mixed"],
            "sameGradeTableGrade": table_layout("same", net.n11, net.n12)[1],
            "rules": spec["rules"],
            "submissionRules": rules.to_dict(),
            "coalitionMode": spec["coalitionMode"],
            "coalition": [ids[i] for i in clique] if spec["coalitionMode"] else [],
            "weights": {"anneal": {"satisfied": obj.violation_int / obj.scale, "extraPeer": obj.extra_int / obj.scale,
                                   "repeatIncidentalPerMeeting": obj.m_int / obj.scale, "repeatListedPerMeeting": obj.alpha_int / obj.scale,
                                   "T0": obj.t0_int / obj.scale, "T1": obj.t1_int / obj.scale, "scale": obj.scale},
                        "cpsat": {"formulation": {"pairs": cpsat_pairs, "extras": cpsat_extras},
                                  "objective": obj.describe()["cpsatObjective"],
                                  "legacyTwoPlus": W_2PLUS_CPSAT, "legacyRepeatScale": CPSAT_REPEAT_SCALE}},
            "objective": obj.describe(),
            "method": method,
            "network": {"reciprocity": round(net.reciprocity, 3), "targetReciprocity": net.target_reciprocity,
                        "pRecip": round(net.p_recip, 3),
                        "withinGradeFrac": round(_within_grade_frac(net), 3),
                        "popularitySigma": net.sigma, "withinBias": net.within_bias, "K": net.K,
                        "mu": net.mu, "omega": net.omega, "nGroups": len(net.groups),
                        "inGroupFrac": round(net.in_group_fraction(), 3)},
            "submission": submission_report(net, lists),
            "submissions": {**sub_summary, "policy": short_list_policy,
                            "records": [s.to_dict(ids) for s in submissions if s.state != "accepted"]},
            "attendance": {"absenceRate": absence_rate, "conflictPolicy": conflict_policy,
                           "explicitAttendance": attendance is not None,
                           "waivedObligations": {str(r + 1): {ids[i]: reason for i, reason in w.items()} for r, w in waivers.items()}},
            "staff": staff.to_dict(ids),
            "solver": {"annealIters": anneal_iters, "cpsatTime": cpsat_time, "workers": workers,
                       "deterministic": deterministic, "feasibilityTime": feasibility_time,
                       "method": method, "cpsatPairs": cpsat_pairs, "cpsatExtras": cpsat_extras,
                       "pipeline": ("pod greedy -> swap repair -> annealing -> CP-SAT (hinted, exact objective) with validated fallbacks"
                                    if method == "hybrid" else "pod greedy -> swap repair with validated fallbacks (no diversity optimisation)")},
            "feasibility": feas,
            "fullModelScreen": full_model,
            "screenBudget": budget.to_dict(),
            "fallbacks": cache.summary(),
            "schedulingStatus": "scheduled",
            "baseline": baseline,
            "versions": _versions(),
            "provenance": provenance,
            "populationSeed": int(net.seed),
            "generator": generator_config,
            "yearSolveSeconds": round(year_time, 1),
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "students": [{"id": ids[i], "grade": grade[i], "submission": submissions[i].state} for i in range(n)],
        "listed": [[ids[j] for j in lists[i]] for i in range(n)],
        "hero": ids[pick_hero(net)],
        "rotations": rotation_records,
        "fairness": fairness,
        "outcomes": outcomes,
        "recurringGroups": recurring,
    }
    trace["leakage"] = {k: v for k, v in leakage_report(trace).items() if k != "perStudent"}
    trace["leakage"]["currentOnlyDistribution"] = windowed_leakage(trace, 1)["worstRetainedWindow"]
    trace["leakage"]["coseatingExposure"] = {"proposed": coseating_exposure(trace),
                                             "random": coseating_exposure(trace, key="tablesRandom")}
    trace["summary"] = summarize(trace)
    if review is not None:
        review.pop("rawPerState", None)
        trace["config"]["screen"] = review
    return trace


RUN_CONFIG_KEYS = ("first_state", "rotations", "anneal_iters", "cpsat_time", "workers", "deterministic",
                   "feasibility_time", "method", "extra_weight", "cpsat_pairs", "cpsat_extras",
                   "absence_rate", "conflict_policy")


def run_config_dict(scenario, seed, **run):
    """The run configuration recorded in every trace's effective inputs.

    Experiment ledgers store the same keys under ``configuration.run``; the
    returned trace must reproduce them exactly (checked by the runner).
    """
    defaults = {"first_state": "mixed", "rotations": ROTATIONS, "anneal_iters": 300_000, "cpsat_time": 3.5,
                "workers": 8, "deterministic": True, "feasibility_time": 20.0, "method": "hybrid",
                "extra_weight": 1.0, "cpsat_pairs": "all", "cpsat_extras": "count", "absence_rate": 0.0,
                "conflict_policy": "stop"}
    unknown = set(run) - set(RUN_CONFIG_KEYS)
    if unknown:
        raise ValueError(f"unknown run configuration keys: {sorted(unknown)}")
    out = {"scenario": scenario, "seed": seed}
    for key in RUN_CONFIG_KEYS:
        out[key] = run.get(key, defaults[key])
    return out


def _within_grade_frac(net: Network) -> float:
    tot = sum(len(f) for f in net.friends)
    same = sum(1 for i, f in enumerate(net.friends) for j in f if net.grade[j] == net.grade[i])
    return same / tot if tot else 0.0


def _coalition_stats(clique, assign, ids):
    by_table = {}
    present = [m for m in clique if assign[m] is not None]
    for m in present:
        by_table.setdefault(assign[m], []).append(ids[m])
    clusters = sorted(by_table.values(), key=len, reverse=True)
    sizes = [len(c) for c in clusters] or [0]
    avg = sum(s * s for s in sizes) / len(clique)  # mean cluster size experienced by a member
    return {"clusters": clusters, "maxCluster": max(sizes), "avgCluster": round(avg, 2),
            "pattern": "+".join(str(s) for s in sizes), "intact": max(sizes) == len(clique),
            "present": len(present)}


def summarize(trace: dict) -> dict:
    rots = trace["rotations"]
    worse = [r["idx"] for r in rots if r["stats"]["repeatPairs"] > r["stats"]["repeatPairsRandom"]]
    s = {
        "pctGe1Min": min(r["stats"]["pctGe1"] for r in rots),
        "pctExactly1Mean": round(float(np.mean([r["stats"]["pctExactly1"] for r in rots])), 2),
        "pctExactly1Min": min(r["stats"]["pctExactly1"] for r in rots),
        "pctGe1RandomMean": round(float(np.mean([r["stats"]["pctGe1Random"] for r in rots])), 2),
        "meanDistinctMetFinal": rots[-1]["stats"]["meanDistinctMet"],
        "meanDistinctMetFinalRandom": rots[-1]["stats"]["meanDistinctMetRandom"],
        "repeatsWorseThanRandomRotations": worse,
        "totalSolveSeconds": round(sum(r["stats"]["solveTime"] for r in rots), 1),
        "maxSolveSeconds": max(r["stats"]["solveTime"] for r in rots),
        "phases": {ph: sum(1 for r in rots if r["stats"]["acceptedPhase"] == ph)
                   for ph in sorted({r["stats"]["acceptedPhase"] for r in rots})},
        "releaseStatuses": {st: sum(1 for r in rots if r["stats"].get("status", "optimized") == st)
                            for st in sorted({r["stats"].get("status", "optimized") for r in rots})},
        "fallbackRotations": [r["idx"] for r in rots if r["stats"].get("status") == "fallback"],
        "incumbentRotations": [r["idx"] for r in rots if r["stats"].get("status") == "incumbent"],
        "optimalityProvenRotations": [r["idx"] for r in rots if r["stats"].get("optimalityProven")],
        "extraCompanionsTotal": sum(r["stats"]["cost"]["extraPeers"] for r in rots),
        "objectiveTotal": round(sum(r["stats"]["cost"].get("objective", 0.0) for r in rots), 2),
        "meanPresent": round(float(np.mean([r["stats"].get("present", len(trace["students"])) for r in rots])), 2),
    }
    if trace["config"]["coalitionMode"]:
        pats = {}
        for r in rots:
            pats[r["coalition"]["pattern"]] = pats.get(r["coalition"]["pattern"], 0) + 1
        s["coalitionIntactRotations"] = sum(1 for r in rots if r["coalition"]["intact"])
        s["coalitionIntactByState"] = {st: sum(1 for r in rots if r["state"] == st and r["coalition"]["intact"])
                                       for st in STATES}
        s["coalitionAvgCluster"] = round(float(np.mean([r["coalition"]["avgCluster"] for r in rots])), 2)
        s["coalitionMaxClusterMean"] = round(float(np.mean([r["coalition"]["maxCluster"] for r in rots])), 2)
        s["coalitionPatterns"] = pats
    return s


def validate_trace(trace: dict) -> None:
    """Raise AssertionError if the trace violates any invariant.

    Every released chart must seat each present student exactly once, meet the
    recorded occupancy targets within capacities, respect grade eligibility,
    honour every present (non-waived) obligation with a present eligible
    companion, avoid staff-prohibited pairs and respect placement restrictions.
    """
    cfg = trace["config"]
    caps = cfg["tableCapacities"]
    tg = cfg["sameGradeTableGrade"]
    students = {s["id"]: s["grade"] for s in trace["students"]}
    ids = [s["id"] for s in trace["students"]]
    listed = {ids[i]: set(l) for i, l in enumerate(trace["listed"])}
    staff = cfg.get("staff") or {}
    prohibited = {frozenset(pair) for pair in staff.get("prohibitedPairs", [])}
    allowed = {k: set(v) for k, v in staff.get("allowedTables", {}).items()}
    assert len(students) == cfg["n"] == sum(caps)
    assert len(trace["rotations"]) == cfg["rotations"]
    for i in range(cfg["n"]):
        assert ids[i] == f"S{i+1:03d}"
    assert cfg.get("schedulingStatus", "scheduled") == "scheduled"
    prev_state = None
    for r in trace["rotations"]:
        state = r["state"]
        assert state in ("same", "mixed")
        if prev_state is not None:
            assert state != prev_state, "states must alternate"
        prev_state = state
        absent = set(r.get("absent", []))
        waived = set((r.get("waivedObligations") or {}).keys())
        present = [i for i in ids if i not in absent]
        targets = r.get("targets", caps)
        assert len(targets) == len(caps) and all(0 <= x <= c for x, c in zip(targets, caps)), "targets exceed capacities"
        assert sum(targets) == len(present), "targets must seat exactly the present students"
        for key in ("tables", "tablesRandom"):
            tables = r[key]
            assert len(tables) == len(caps)
            seen = []
            for t, tbl in enumerate(tables):
                assert len(tbl) == targets[t], f"{key} rotation {r['idx']} table {t}: {len(tbl)} != {targets[t]}"
                seen.extend(tbl)
                if state == "same":
                    assert all(students[s] == tg[t] for s in tbl), f"cross-grade table in same-grade rotation {r['idx']}"
            assert sorted(seen) == sorted(present), "every present student exactly once"
        table_of = {}
        for t, tbl in enumerate(r["tables"]):
            for s in tbl:
                table_of[s] = t
        for s, L in listed.items():
            if not L or s in absent or s in waived:
                continue
            mates = set(r["tables"][table_of[s]]) - {s}
            elig = {j for j in L if (state == "mixed" or students[j] == students[s]) and j not in absent}
            assert mates & elig, f"rotation {r['idx']}: {s} has no listed peer at the table"
            a = r["anchors"].get(s)
            assert a in mates and a in L, f"rotation {r['idx']}: bad anchor for {s}"
        for pair in prohibited:
            a, b = tuple(pair)
            if a in table_of and b in table_of:
                assert table_of[a] != table_of[b], f"rotation {r['idx']}: prohibited pair {a},{b} share a table"
        for s, tables_ok in allowed.items():
            if s in table_of:
                assert table_of[s] in tables_ok, f"rotation {r['idx']}: {s} seated outside its allowed tables"
        obligated = [s for s, L in listed.items() if L and s not in absent and s not in waived]
        assert r["stats"]["pctGe1"] == (100.0 if obligated else 0.0)
        release = r.get("release")
        if release is not None:
            assert release["validation"]["valid"] is True
            assert release["status"] in ("optimized", "incumbent", "fallback")
            if release.get("optimalityProven"):
                assert release["accepted"] == "cpsat"


def make_all(seed: int = 7, scenarios=None, log=print, mu: float = 0.0, omega: float = 0.0,
             cross_grade_group_frac: float = 0.0, short_list_policy: str = "review", solver_seed=None,
             generator_config=None, nonsubmit_frac: float = 0.0, list_cap: int | None = None,
             review_decisions=None, screen_budget=None, **solver_kw) -> dict[str, dict]:
    gen = {k: v.default for k, v in inspect.signature(make_cohort).parameters.items()
           if v.default is not inspect.Parameter.empty}
    gen.update(generator_config or {})
    gen.update(seed=seed, mu=mu, omega=omega, cross_grade_group_frac=cross_grade_group_frac)
    net = make_cohort(**gen)
    out = {}
    for name in scenarios or list(SCENARIOS):
        lists, extra = build_lists(net, name, short_list_policy=short_list_policy, nonsubmit_frac=nonsubmit_frac,
                                   list_cap=list_cap, review_decisions=review_decisions, screen_budget=screen_budget)
        if log:
            log(f"== scenario {name}: {SCENARIOS[name]['title']}")
            if "screen" in extra:
                log(f"   screen: flagged {extra['screen']['nFlagged']} students, returned {extra['screen']['nReturned']}; "
                    f"honest students returned: {len(extra['screen']['honestFlagged'])}")
        trace = run_year(net, lists, name, seed=seed if solver_seed is None else solver_seed,
                         log=log, generator_config={**gen, "short_list_policy": short_list_policy,
                                                    "nonsubmit_frac": nonsubmit_frac, "list_cap": list_cap},
                         submissions=extra["submissions"], short_list_policy=short_list_policy,
                         screen_budget=screen_budget, review_decisions=review_decisions, **solver_kw)
        if "screen" in extra:
            extra["screen"].pop("rawPerState", None)
            if "afterResubmission" in extra["screen"]:
                extra["screen"]["afterResubmission"].pop("rawPerState", None)
            trace["config"]["screen"] = {**trace["config"].get("screen", {}), **extra["screen"]}
        if "listedInitial" in extra:
            ids = net.ids()
            trace["listedInitial"] = [[ids[j] for j in l] for l in extra["listedInitial"]]
        if "diagnosticScreen" in extra:
            extra["diagnosticScreen"].pop("rawPerState", None)
            trace["config"]["diagnosticScreen"] = extra["diagnosticScreen"]
        validate_trace(trace)
        out[name] = trace
    return out
