"""Scenario definitions, the full-year runner, trace assembly and validation."""
from __future__ import annotations

import inspect
import random
import time
from datetime import datetime, timezone

import numpy as np

from .baseline import expected_distinct, expected_friend_coverage
from .generator import (Network, make_cohort, honest_lists, coalition_lists, student_id, submission_report)
from .privacy import leakage_report
from .provenance import source_provenance, trace_provenance
from .screens import run_screens
from .solver import (Problem, table_layout, solve_rotation, random_assignment, feasibility_certificate,
                     InfeasibleInputError, VIOL, W_EXTRA, W_M, W_ALPHA, SCALE, T0, T1, W_2PLUS_CPSAT,
                     CPSAT_REPEAT_SCALE)

ROTATIONS = 16
STATES = ("mixed", "same")

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
SCENARIOS = {name: SCENARIOS[name] for name in (
    "honest", "coalition_none", "coalition_min4", "coalition_stratified",
    "coalition_shared_anchor", "coalition_screened")}


class SubmissionReviewRequired(ValueError):
    """Approved input is required before a screen-enabled year can be seated."""


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


def build_lists(net: Network, scenario: str, short_list_policy: str = "none"):
    """Return (lists_used, extra) where extra carries the screen report etc."""
    spec = SCENARIOS[scenario]
    mode = spec["coalitionMode"]
    extra = {}
    base = honest_lists(net, short_list_policy=short_list_policy)
    caps_by_state, _ = _caps_by_state(net)
    if mode is None:
        lists = base
        if spec["rules"]["screens"]:
            extra["screen"] = _screen_report(lists, net, caps_by_state, flagged_expected=False)
    elif mode in ("k1", "min4", "stratified"):
        lists = coalition_lists(net, mode, base)
    elif mode == "shared_anchor":
        lists = shared_anchor_lists(net, base)
        extra["diagnosticScreen"] = _screen_report(
            lists, net, caps_by_state, flagged_expected=True,
            coalition=coalition_members(net, scenario))
    elif mode == "screened":
        first = coalition_lists(net, "stratified", base)
        rep = _screen_report(first, net, caps_by_state, flagged_expected=True)
        extra["screen"] = rep
        extra["listedInitial"] = first
        # A specified adversarial response within the internal four-of-five family.
        lists = coalition_lists(net, "min4", base)
        rep["resubmission"] = "adversarial: strongest passing 4-of-5 wiring (omission star)"
        rep["afterResubmission"] = _screen_report(lists, net, caps_by_state, flagged_expected=False)
    else:
        raise ValueError(mode)
    return lists, extra


def _ids(seq):
    return [student_id(m) for m in seq]


def _screen_report(lists, net: Network, caps_by_state, flagged_expected: bool, coalition=None):
    _, grade_caps = _caps_by_state(net)
    r = run_screens(lists, list(int(g) for g in net.grade), caps_by_state,
                    caps_by_grade_by_state={"same": grade_caps})
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


def run_year(net: Network, lists, scenario: str, seed: int = 7, first_state: str = "mixed",
             anneal_iters: int = 300_000, cpsat_time: float = 3.5, workers: int = 8,
             deterministic: bool = True, feasibility_time: float = 20.0, log=print,
             rotations: int = ROTATIONS, generator_config=None) -> dict:
    spec = SCENARIOS[scenario]
    if rotations < 1:
        raise ValueError("rotations must be positive")
    n = net.n
    if len(lists) != n or any(len(l) != len(set(l)) or i in l or
                             any(not isinstance(j, (int, np.integer)) or not 0 <= j < n for j in l)
                             for i, l in enumerate(lists)):
        raise ValueError("submitted lists must have distinct, valid, non-self student indices")
    grade = [int(g) for g in net.grade]
    ids = net.ids()
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
    submitters = [i for i in range(n) if lists[i]]
    clique = coalition_members(net, scenario)
    caps_by_state, caps_same_by_grade = _caps_by_state(net)
    review = None
    if spec["rules"]["screens"]:
        review = _screen_report(lists, net, caps_by_state, flagged_expected=False, coalition=clique)
        if any(review[k] for k in ("returnedStudents", "unresolvedCandidates", "unresolvedChecks", "min4Violations", "sameGradeViolations", "ineligible")):
            raise SubmissionReviewRequired(
                f"{scenario}: submissions need review before seating "
                f"(returned={review['nReturned']}, unresolved={review['nUnresolved']})")
    run_config = {"scenario": scenario, "seed": seed, "first_state": first_state, "rotations": rotations,
                  "anneal_iters": anneal_iters, "cpsat_time": cpsat_time, "workers": workers,
                  "deterministic": deterministic, "feasibility_time": feasibility_time}
    provenance = trace_provenance(net, lists, run_config, generator_config)

    # pre-solve feasibility certificates (hard constraints only) for both states
    feas = {}
    for state in STATES:
        caps, tg = table_layout(state, net.n11, net.n12)
        p0 = Problem(grade, lists, caps, tg, hist_m, state, history_alpha=hist_a)
        t0 = time.perf_counter()
        try:
            status, _ = feasibility_certificate(p0, time_limit=feasibility_time, workers=workers, seed=seed,
                                                deterministic=deterministic)
        except InfeasibleInputError as e:
            status = f"INFEASIBLE_INPUT: {e}"
        feas[state] = {"status": status, "seconds": round(time.perf_counter() - t0, 2)}
        if log:
            log(f"  [{scenario}] feasibility ({state}): {status} in {feas[state]['seconds']}s")
        if status.startswith("INFEASIBLE"):
            raise InfeasibleInputError(f"{scenario}: the submitted lists admit no seating in {state} rotations ({status})")

    t_year = time.perf_counter()
    for r in range(rotations):
        state = state_for(r, first_state)
        caps, tg = table_layout(state, net.n11, net.n12)
        p = Problem(grade, lists, caps, tg, hist_m, state, prev_tables=prev, history_alpha=hist_a)
        assign, info = solve_rotation(p, seed=seed * 1000 + r, anneal_iters=anneal_iters,
                                      cpsat_time=cpsat_time, workers=workers, deterministic=deterministic)
        bad = p.check(assign)
        assert not bad, f"{scenario} rotation {r+1}: {len(bad)} submitters without a listed peer"
        members = p.members_of(assign)

        rng_r = random.Random(f"{seed}-random-{r}")
        rassign = random_assignment(p, rng_r)
        rmembers = p.members_of(rassign)
        for t in range(p.T):
            assert len(rmembers[t]) == caps[t]

        cnt = p.counts(assign, members)
        rcnt = p.counts(rassign, rmembers)
        anchors, ranchors = {}, {}
        for i in submitters:
            a = _anchor_for(i, members[assign[i]], p.adj[i], hist_total)
            if a is not None:
                anchors[ids[i]] = ids[a]
            ra = _anchor_for(i, rmembers[rassign[i]], p.adj[i], hist_rand)
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

        ns = len(submitters)
        stats = {
            "pctGe1": _pct(sum(1 for i in submitters if cnt[i] >= 1), ns),
            "pctExactly1": _pct(sum(1 for i in submitters if cnt[i] == 1), ns),
            "pctGe2": _pct(sum(1 for i in submitters if cnt[i] >= 2), ns),
            "pctGe1Random": _pct(sum(1 for i in submitters if rcnt[i] >= 1), ns),
            "pctExactly1Random": _pct(sum(1 for i in submitters if rcnt[i] == 1), ns),
            "pctGe2Random": _pct(sum(1 for i in submitters if rcnt[i] >= 2), ns),
            "meanDistinctMet": round(float(met), 2),
            "meanDistinctMetRandom": round(float(rmet), 2),
            "repeatPairs": rep,
            "repeatPairsRandom": rrep,
            "cost": info["final"],
            "acceptedPhase": info["accepted"],
            "cpsatStatus": info.get("cpsat", {}).get("status"),
            "solveTime": round(info["time"]["total"], 2),
            "fallbackTime": round(info["time"]["fallback"], 2),
            "annealRetries": info.get("annealRetries", 0),
        }
        rot = {
            "idx": r + 1,
            "state": state,
            "tables": [[ids[i] for i in m] for m in members],
            "tablesRandom": [[ids[i] for i in m] for m in rmembers],
            "anchors": anchors,
            "anchorsRandom": ranchors,
            "stats": stats,
            "pipeline": [{"name": name, "tables": [[ids[i] for i in m] for m in p.members_of(info["snapshots"][key])],
                          "cost": info[key], "seconds": round(info["time"][time_key], 4)}
                         for name, key, time_key in (("construction", "greedy", "greedy"),
                                                    ("repair", "repair", "repair"),
                                                    ("annealing", "anneal", "anneal"),
                                                    ("final", "final", "cpsat"))],
        }
        rot["pipeline"][-1]["seconds"] = round(info["time"]["cpsat"] + info["time"]["fallback"], 4)
        if spec["coalitionMode"] is not None:
            rot["coalition"] = _coalition_stats(clique, assign, ids)
            rot["coalitionRandom"] = _coalition_stats(clique, rassign, ids)
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
    }
    baseline["expectedFriendCoverageSchedule"] = round(
        (baseline["expectedFriendCoverageMixed"] * states.count("mixed") + baseline["expectedFriendCoverageSame"] * states.count("same")) / rotations, 3)

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
            "coalitionMode": spec["coalitionMode"],
            "coalition": [ids[i] for i in clique] if spec["coalitionMode"] else [],
            "weights": {"anneal": {"satisfied": VIOL / SCALE, "extraPeer": W_EXTRA / SCALE,
                                   "repeatIncidentalPerMeeting": W_M / SCALE, "repeatListedPerMeeting": W_ALPHA / SCALE,
                                   "T0": T0 / SCALE, "T1": T1 / SCALE},
                        "cpsat": {"twoPlus": W_2PLUS_CPSAT, "repeatScale": CPSAT_REPEAT_SCALE}},
            "network": {"reciprocity": round(net.reciprocity, 3), "targetReciprocity": net.target_reciprocity,
                        "pRecip": round(net.p_recip, 3),
                        "withinGradeFrac": round(_within_grade_frac(net), 3),
                        "popularitySigma": net.sigma, "withinBias": net.within_bias, "K": net.K,
                        "mu": net.mu, "omega": net.omega, "nGroups": len(net.groups),
                        "inGroupFrac": round(net.in_group_fraction(), 3)},
            "submission": submission_report(net, lists),
            "solver": {"annealIters": anneal_iters, "cpsatTime": cpsat_time, "workers": workers,
                       "deterministic": deterministic, "feasibilityTime": feasibility_time,
                       "pipeline": "pod greedy -> swap repair -> annealing -> CP-SAT (hinted)"},
            "feasibility": feas,
            "baseline": baseline,
            "versions": _versions(),
            "provenance": provenance,
            "populationSeed": int(net.seed),
            "generator": generator_config,
            "yearSolveSeconds": round(year_time, 1),
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "students": [{"id": ids[i], "grade": grade[i]} for i in range(n)],
        "listed": [[ids[j] for j in lists[i]] for i in range(n)],
        "hero": ids[pick_hero(net)],
        "rotations": rotation_records,
        "fairness": fairness,
    }
    trace["leakage"] = {k: v for k, v in leakage_report(trace).items() if k != "perStudent"}
    trace["summary"] = summarize(trace)
    if review is not None:
        trace["config"]["screen"] = review
    return trace


def _within_grade_frac(net: Network) -> float:
    tot = sum(len(f) for f in net.friends)
    same = sum(1 for i, f in enumerate(net.friends) for j in f if net.grade[j] == net.grade[i])
    return same / tot if tot else 0.0


def _coalition_stats(clique, assign, ids):
    by_table = {}
    for m in clique:
        by_table.setdefault(assign[m], []).append(ids[m])
    clusters = sorted(by_table.values(), key=len, reverse=True)
    sizes = [len(c) for c in clusters]
    avg = sum(s * s for s in sizes) / len(clique)  # mean cluster size experienced by a member
    return {"clusters": clusters, "maxCluster": max(sizes), "avgCluster": round(avg, 2),
            "pattern": "+".join(str(s) for s in sizes), "intact": max(sizes) == len(clique)}


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
    """Raise AssertionError if the trace violates any invariant."""
    cfg = trace["config"]
    caps = cfg["tableCapacities"]
    tg = cfg["sameGradeTableGrade"]
    students = {s["id"]: s["grade"] for s in trace["students"]}
    ids = [s["id"] for s in trace["students"]]
    listed = {ids[i]: set(l) for i, l in enumerate(trace["listed"])}
    assert len(students) == cfg["n"] == sum(caps)
    assert len(trace["rotations"]) == cfg["rotations"]
    for i in range(cfg["n"]):
        assert ids[i] == f"S{i+1:03d}"
    prev_state = None
    for r in trace["rotations"]:
        state = r["state"]
        assert state in ("same", "mixed")
        if prev_state is not None:
            assert state != prev_state, "states must alternate"
        prev_state = state
        for key in ("tables", "tablesRandom"):
            tables = r[key]
            assert len(tables) == len(caps)
            seen = []
            for t, tbl in enumerate(tables):
                assert len(tbl) == caps[t], f"{key} rotation {r['idx']} table {t}: {len(tbl)} != {caps[t]}"
                seen.extend(tbl)
                if state == "same":
                    assert all(students[s] == tg[t] for s in tbl), f"cross-grade table in same-grade rotation {r['idx']}"
            assert sorted(seen) == ids, "every student exactly once"
        table_of = {}
        for t, tbl in enumerate(r["tables"]):
            for s in tbl:
                table_of[s] = t
        for s, L in listed.items():
            if not L:
                continue
            mates = set(r["tables"][table_of[s]]) - {s}
            elig = {j for j in L if state == "mixed" or students[j] == students[s]}
            assert mates & elig, f"rotation {r['idx']}: {s} has no listed peer at the table"
            a = r["anchors"].get(s)
            assert a in mates and a in L, f"rotation {r['idx']}: bad anchor for {s}"
        assert r["stats"]["pctGe1"] == (100.0 if any(listed.values()) else 0.0)


def make_all(seed: int = 7, scenarios=None, log=print, mu: float = 0.0, omega: float = 0.0,
             cross_grade_group_frac: float = 0.0, short_list_policy: str = "none", solver_seed=None,
             generator_config=None, **solver_kw) -> dict[str, dict]:
    gen = {k: v.default for k, v in inspect.signature(make_cohort).parameters.items()
           if v.default is not inspect.Parameter.empty}
    gen.update(generator_config or {})
    gen.update(seed=seed, mu=mu, omega=omega, cross_grade_group_frac=cross_grade_group_frac)
    net = make_cohort(**gen)
    out = {}
    for name in scenarios or list(SCENARIOS):
        lists, extra = build_lists(net, name, short_list_policy=short_list_policy)
        if log:
            log(f"== scenario {name}: {SCENARIOS[name]['title']}")
            if "screen" in extra:
                log(f"   screen: flagged {extra['screen']['nFlagged']} students, returned {extra['screen']['nReturned']}; "
                    f"honest students returned: {len(extra['screen']['honestFlagged'])}")
        trace = run_year(net, lists, name, seed=seed if solver_seed is None else solver_seed,
                         log=log, generator_config={**gen, "short_list_policy": short_list_policy}, **solver_kw)
        if "screen" in extra:
            trace["config"]["screen"] = extra["screen"]
        if "listedInitial" in extra:
            ids = net.ids()
            trace["listedInitial"] = [[ids[j] for j in l] for l in extra["listedInitial"]]
        if "diagnosticScreen" in extra:
            trace["config"]["diagnosticScreen"] = extra["diagnosticScreen"]
        validate_trace(trace)
        out[name] = trace
    return out
