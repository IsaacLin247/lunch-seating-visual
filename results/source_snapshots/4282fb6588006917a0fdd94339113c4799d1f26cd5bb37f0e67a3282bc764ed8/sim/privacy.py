"""Chart-only inference of submitted lists (output leakage probe).

Anyone who sees the seating charts and knows the rules can reason: a submitter
i had a listed peer at their table in every rotation, so every observed
tablemate set T_{i,r} contains at least one listed name; if lists have at most
K names all year, the list is a hitting set of size <= K for the family
{T_{i,r}}.  A name j is *forced* if every hitting set of size <= K contains j,
i.e. the minimum hitting set of the family with j removed exceeds K.

This module reproduces that inference exactly (minimum hitting set by bitmask
dynamic programming over the rotations) and scores it against the true lists,
so the leakage of a trace can be reported as a number instead of assumed away.
It never reads lists or anchors during inference.
"""
from __future__ import annotations

from functools import lru_cache


def tablemate_sets(rotations, ids, key="tables"):
    peers = {i: [] for i in ids}
    for r in rotations:
        for tbl in r[key]:
            s = set(tbl)
            for i in tbl:
                peers[i].append(s - {i})
    return peers


def min_hitting_set(patterns, n_rot):
    """patterns: name -> bitmask of rotations in which the name was a tablemate.
    Returns a minimum-size list of names hitting every rotation, or None."""
    unique = {m for m in patterns.values() if m}
    kept = {m for m in unique if not any(m != o and (m & o) == m for o in unique)}   # drop dominated
    full = (1 << n_rot) - 1
    by_bit = [[m for m in kept if (m >> b) & 1] for b in range(n_rot)]
    if any(not lst for lst in by_bit):
        return None

    @lru_cache(maxsize=None)
    def go(mask):
        if mask == full:
            return ()
        b = min((b for b in range(n_rot) if not (mask >> b) & 1), key=lambda b: len(by_bit[b]))
        best = None
        for m in by_bit[b]:
            child = go(mask | m)
            if child is not None and (best is None or len(child) + 1 < len(best)):
                best = (m,) + child
        return best

    masks = go(0)
    if masks is None:
        return None
    return [next(j for j, m in patterns.items() if m == p) for p in masks]


def infer_forced_names(peers_by_rotation, k_max):
    """Names that every hitting set of size <= k_max must contain."""
    n_rot = len(peers_by_rotation)
    names = set().union(*peers_by_rotation) if peers_by_rotation else set()
    patterns = {j: sum(1 << r for r, t in enumerate(peers_by_rotation) if j in t) for j in names}
    initial = min_hitting_set(patterns, n_rot)
    if initial is None or len(initial) > k_max:
        return [], initial
    forced = []
    for j in initial:
        other = min_hitting_set({a: b for a, b in patterns.items() if a != j}, n_rot)
        if other is None or len(other) > k_max:
            forced.append(j)
    return sorted(forced), initial


def leakage_report(trace, k_max=None, key="tables", public_list_lengths=None):
    """Infer from charts and public constraints, then separately score truth.

    Submitter identities, the static-list rule and ``k_max`` are assumed public.
    By default the declared cap is config.rules.maxList, config.K, or the model's
    documented cap of eight; the private maximum observed list length is never
    used. Optional exact lengths must be public metadata supplied by the caller.

    Under an upper-cap-only model, a forced set identifies the complete list
    only if it fills the public cap (or the entire possible peer universe).
    Recovering every actual positive entry in a shorter private list is a
    separate ground-truth score, not proof that no additional names are possible.
    """
    ids = [s["id"] for s in trace["students"]]
    truth = dict(zip(ids, (set(l) for l in trace["listed"])))
    cfg = trace.get("config", {})
    if k_max is None:
        k_max = cfg.get("rules", {}).get("maxList", cfg.get("K", 8))
    if not isinstance(k_max, int) or k_max < 0:
        raise ValueError("the public list cap must be a nonnegative integer")
    public_list_lengths = public_list_lengths or {}
    for i, length in public_list_lengths.items():
        if i not in truth or not isinstance(length, int) or not 0 <= length <= min(k_max, len(ids) - 1):
            raise ValueError("public exact lengths must name existing students and obey the public cap")
    peers = tablemate_sets(trace["rotations"], ids, key)
    forced_edges, students_hit, correct, fully, recovered, inconsistent = 0, 0, 0, [], [], []
    per_student = {}
    for i in ids:
        if not truth[i]:
            continue
        cap = public_list_lengths.get(i, k_max)
        forced, minimum = infer_forced_names(peers[i], cap)
        if minimum is None or len(minimum) > cap or cap == 0:
            inconsistent.append(i)
            continue
        if forced:
            students_hit += 1
            forced_edges += len(forced)
            correct += sum(1 for j in forced if j in truth[i])
            if len(forced) == min(cap, len(ids) - 1):
                fully.append(i)
            if truth[i] <= set(forced):
                recovered.append(i)
            per_student[i] = forced
    n_edges = sum(len(l) for l in trace["listed"])
    return {"kMax": k_max, "rotationsObserved": len(trace["rotations"]), "forcedEdges": forced_edges,
            "forcedEdgesCorrect": correct, "studentsWithForcedEdge": students_hit,
            "fullyDeterminedStudents": fully, "completeTruePositiveRecoveryStudents": recovered,
            "inconsistentObservationStudents": inconsistent,
            "publicExactLengths": dict(public_list_lengths),
            "inferenceAssumptions": {"knownSubmitterIdentities": True, "staticLists": True,
                                     "knownUpperCap": True, "usesPrivateLengthsForInference": False},
            "submittedEdges": n_edges,
            "fractionOfEdgesForced": round(forced_edges / n_edges, 4) if n_edges else 0.0,
            "perStudent": per_student}
