"""Scenario definitions, the full-year runner, trace assembly and validation."""
from __future__ import annotations

import random
import time
from datetime import datetime, timezone

import numpy as np

from .generator import Network, generate_network, honest_lists, coalition_lists, student_id, apply_rules
from .screens import run_screens
from .solver import (Problem, table_layout, solve_rotation, random_assignment,
                     W_2PLUS, W_INCIDENTAL, W_LISTED, CPSAT_REPEAT_SCALE)

ROTATIONS = 16
STATES = ("mixed", "same")

SCENARIOS = {
    "honest": {
        "title": "The whole room",
        "short": "Honest lists",
        "description": "Every student submits their true friends (8 names). Random status quo vs. the proposed system.",
        "coalitionMode": None,
        "rules": {"min4": True, "screens": True},
    },
    "coalition_none": {
        "title": "Gaming it: no defenses",
        "short": "No defenses",
        "description": "Six students each list only the next member of their group (k=1 chains). No submission rules, no screens.",
        "coalitionMode": "k1",
        "rules": {"min4": False, "screens": False},
    },
    "coalition_min4": {
        "title": "Gaming it: min-4 rule",
        "short": "Min-4 rule",
        "description": "The same six must list at least 4 names; they list 4 of their 5 co-members with adversarial wiring. Screens off.",
        "coalitionMode": "min4",
        "rules": {"min4": True, "screens": False},
    },
    "coalition_screened": {
        "title": "Gaming it: screens on",
        "short": "Screens on",
        "description": "Min-4 rule plus the pre-solve screens: the group is flagged, returned for diversification, and resubmits honest lists.",
        "coalitionMode": "screened",
        "rules": {"min4": True, "screens": True},
    },
}


def pick_hero(net: Network) -> int:
    """A mid-popularity junior who is not in the planted clique."""
    juniors = [i for i in range(net.n11) if i not in net.clique]
    juniors.sort(key=lambda i: net.popularity[i])
    return juniors[len(juniors) // 2]


def state_for(rot_idx: int, first_state: str = "mixed") -> str:
    k = STATES.index(first_state)
    return STATES[(k + rot_idx) % 2]


def build_lists(net: Network, scenario: str):
    """Return (lists_used, extra) where extra carries screen results etc."""
    spec = SCENARIOS[scenario]
    mode = spec["coalitionMode"]
    extra = {}
    base = honest_lists(net)
    if mode is None:
        lists = base
        if spec["rules"]["screens"]:
            extra["screen"] = _screen_report(lists, net, flagged_expected=False)
    elif mode == "k1":
        lists = coalition_lists(net, "k1", base)
    elif mode == "min4":
        lists = coalition_lists(net, "min4", base)
    elif mode == "screened":
        first = coalition_lists(net, "min4", base)
        rep = _screen_report(first, net, flagged_expected=True)
        extra["screen"] = rep
        extra["listedInitial"] = first
        # flagged students are returned for diversification and resubmit
        # honest lists (their true friends, rules applied)
        lists = [list(l) for l in first]
        rng = np.random.default_rng([net.seed, 9])
        for i in run_screens(first)["flaggedStudents"]:
            lists[i] = apply_rules(list(net.friends[i]), i, net, rng)
        rep["afterResubmission"] = _screen_report(lists, net, flagged_expected=False)
    else:
        raise ValueError(mode)
    return lists, extra


def _screen_report(lists, net: Network, flagged_expected: bool):
    r = run_screens(lists)
    return {
        "flags": [{**f, "members": [student_id(m) for m in f["members"]],
                   **({"kernel": [student_id(m) for m in f["kernel"]]} if "kernel" in f else {})}
                  for f in r["flags"]],
        "flaggedStudents": [student_id(m) for m in r["flaggedStudents"]],
        "nFlagged": len(r["flaggedStudents"]),
        "coalitionFlagged": all(m in r["flaggedStudents"] for m in net.clique) if flagged_expected else None,
        "honestFlagged": [student_id(m) for m in r["flaggedStudents"] if m not in net.clique],
    }


def _anchor_for(i, table_members, adj, history):
    peers = [j for j in table_members if j in adj]
    if not peers:
        return None
    peers.sort(key=lambda j: (history[i][j], j))
    return peers[0]


def _pct(num, den):
    return round(100.0 * num / den, 2) if den else 0.0


def run_year(net: Network, lists, scenario: str, seed: int = 7, first_state: str = "mixed",
             anneal_iters: int = 300_000, cpsat_time: float = 3.5, workers: int = 16,
             deterministic: bool = True, log=print) -> dict:
    spec = SCENARIOS[scenario]
    n = net.n
    grade = [int(g) for g in net.grade]
    ids = net.ids()
    hist = [[0] * n for _ in range(n)]
    hist_rand = [[0] * n for _ in range(n)]
    prev = None
    rotations = []
    submitters = [i for i in range(n) if lists[i]]
    clique = list(net.clique)
    t_year = time.perf_counter()
    for r in range(ROTATIONS):
        state = state_for(r, first_state)
        caps, tg = table_layout(state, net.n11, net.n12)
        p = Problem(grade, lists, caps, tg, hist, state, prev_tables=prev)
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
            a = _anchor_for(i, members[assign[i]], p.adj[i], hist)
            if a is not None:
                anchors[ids[i]] = ids[a]
            ra = _anchor_for(i, rmembers[rassign[i]], p.adj[i], hist_rand)
            if ra is not None:
                ranchors[ids[i]] = ids[ra]

        # repeats relative to history (pairs seated together that have met before)
        def n_repeats(ms, h):
            k = 0
            for m in ms:
                for x in range(len(m)):
                    for y in range(x + 1, len(m)):
                        if h[m[x]][m[y]] > 0:
                            k += 1
            return k
        rep = n_repeats(members, hist)
        rrep = n_repeats(rmembers, hist_rand)
        for ms, h in ((members, hist), (rmembers, hist_rand)):
            for m in ms:
                for x in m:
                    hx = h[x]
                    for y in m:
                        if x != y:
                            hx[y] += 1
        met = np.mean([sum(1 for b in range(n) if hist[a][b] > 0) for a in range(n)])
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
        }
        rot = {
            "idx": r + 1,
            "state": state,
            "tables": [[ids[i] for i in m] for m in members],
            "tablesRandom": [[ids[i] for i in m] for m in rmembers],
            "anchors": anchors,
            "anchorsRandom": ranchors,
            "stats": stats,
        }
        if spec["coalitionMode"] is not None:
            rot["coalition"] = _coalition_stats(clique, assign, ids)
            rot["coalitionRandom"] = _coalition_stats(clique, rassign, ids)
        rotations.append(rot)
        prev = members
        if log:
            c = rot.get("coalition")
            log(f"  [{scenario}] rotation {r+1:2d} {state:5s} ge1={stats['pctGe1']:5.1f}% "
                f"exactly1={stats['pctExactly1']:5.1f}% met={stats['meanDistinctMet']:5.1f} "
                f"(rand {stats['meanDistinctMetRandom']:5.1f}) cost={info['final']['total']:5d} "
                f"{info['accepted']:6s} {stats['solveTime']:5.1f}s"
                + (f" coalition max={c['maxCluster']} avg={c['avgCluster']}" if c else ""))
    year_time = time.perf_counter() - t_year

    trace = {
        "config": {
            "scenario": scenario,
            "title": spec["title"],
            "short": spec["short"],
            "description": spec["description"],
            "seed": seed,
            "n": n, "n11": net.n11, "n12": net.n12, "K": 8,
            "rotations": ROTATIONS,
            "firstState": first_state,
            "tableCapacities": table_layout("mixed", net.n11, net.n12)[0],
            "sameGradeTableGrade": table_layout("same", net.n11, net.n12)[1],
            "rules": spec["rules"],
            "coalitionMode": spec["coalitionMode"],
            "coalition": [ids[i] for i in clique] if spec["coalitionMode"] else [],
            "weights": {"twoPlus": W_2PLUS, "incidentalRepeat": W_INCIDENTAL, "listedRepeat": W_LISTED,
                        "cpsatRepeatScale": CPSAT_REPEAT_SCALE},
            "network": {"reciprocity": round(net.reciprocity, 3),
                        "withinGradeFrac": round(_within_grade_frac(net), 3),
                        "popularitySigma": 0.6, "withinBias": 9.0},
            "solver": {"annealIters": anneal_iters, "cpsatTime": cpsat_time, "workers": workers,
                       "deterministic": deterministic, "pipeline": "pod greedy -> swap repair -> annealing -> CP-SAT (hinted)"},
            "yearSolveSeconds": round(year_time, 1),
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "students": [{"id": ids[i], "grade": grade[i]} for i in range(n)],
        "listed": [[ids[j] for j in lists[i]] for i in range(n)],
        "hero": ids[pick_hero(net)],
        "rotations": rotations,
    }
    trace["summary"] = summarize(trace)
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
            "intact": max(sizes) == len(clique)}


def summarize(trace: dict) -> dict:
    rots = trace["rotations"]
    s = {
        "pctGe1Min": min(r["stats"]["pctGe1"] for r in rots),
        "pctExactly1Mean": round(float(np.mean([r["stats"]["pctExactly1"] for r in rots])), 2),
        "pctGe1RandomMean": round(float(np.mean([r["stats"]["pctGe1Random"] for r in rots])), 2),
        "meanDistinctMetFinal": rots[-1]["stats"]["meanDistinctMet"],
        "meanDistinctMetFinalRandom": rots[-1]["stats"]["meanDistinctMetRandom"],
        "totalSolveSeconds": round(sum(r["stats"]["solveTime"] for r in rots), 1),
    }
    if trace["config"]["coalitionMode"]:
        s["coalitionIntactRotations"] = sum(1 for r in rots if r["coalition"]["intact"])
        s["coalitionAvgCluster"] = round(float(np.mean([r["coalition"]["avgCluster"] for r in rots])), 2)
        s["coalitionMaxClusterMean"] = round(float(np.mean([r["coalition"]["maxCluster"] for r in rots])), 2)
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
        # the guarantee
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
        assert r["stats"]["pctGe1"] == 100.0


def make_all(seed: int = 7, scenarios=None, log=print, **solver_kw) -> dict[str, dict]:
    net = generate_network(seed=seed)
    out = {}
    for name in scenarios or list(SCENARIOS):
        lists, extra = build_lists(net, name)
        if log:
            log(f"== scenario {name}: {SCENARIOS[name]['title']}")
            if "screen" in extra:
                log(f"   screens: flagged {extra['screen']['nFlagged']} students; "
                    f"honest false positives: {len(extra['screen']['honestFlagged'])}")
        trace = run_year(net, lists, name, seed=seed, log=log, **solver_kw)
        if "screen" in extra:
            trace["config"]["screen"] = extra["screen"]
        if "listedInitial" in extra:
            ids = net.ids()
            trace["listedInitial"] = [[ids[j] for j in l] for l in extra["listedInitial"]]
        validate_trace(trace)
        out[name] = trace
    return out
