"""Structural analysis of coalition wirings.

For a coalition whose members list only each other, every feasible seating
induces a partition of the coalition into closed parts (each member has a
listed co-member in their part).  The member-weighted mean cluster size of a
partition is sum |P|^2 / |coalition|.  Its minimum over all valid partitions is
a lower bound on the cohesion any solver must grant the coalition, independent
of seed, budget or history.  best_four_of_five_wiring() maximises that bound
over every 4-of-5 wiring of six members (each member omits exactly one
co-member), which is the attacker's best structural guarantee under the min-4
rule with purely internal lists.
"""
from __future__ import annotations

from itertools import product

from .screens import coercion_screen


def set_partitions(xs):
    if not xs:
        yield []
        return
    a, *rest = xs
    for p in set_partitions(rest):
        yield [[a]] + [x[:] for x in p]
        for k in range(len(p)):
            q = [x[:] for x in p]
            q[k].append(a)
            yield q


_PARTITIONS6 = list(set_partitions(list(range(6))))


def wiring_from_omissions(omitted):
    """omitted[i] = the one co-member that member i does not list."""
    m = len(omitted)
    return [sorted(set(range(m)) - {i, omitted[i]}) for i in range(m)]


def cohesion_bound(lists):
    """(min mean cluster, min largest cluster, min extra peers) over valid partitions."""
    m = len(lists)
    L = [set(l) for l in lists]
    parts = _PARTITIONS6 if m == 6 else list(set_partitions(list(range(m))))
    best = None
    for p in parts:
        ok = True
        extra = 0
        for part in p:
            ps = set(part)
            for i in part:
                c = len(L[i] & ps)
                if c == 0:
                    ok = False
                    break
                extra += c - 1
            if not ok:
                break
        if not ok:
            continue
        mean = sum(len(t) ** 2 for t in p) / m
        cand = (mean, max(map(len, p)), extra)
        if best is None:
            best = list(cand)
        else:
            best = [min(best[0], cand[0]), min(best[1], cand[1]), min(best[2], cand[2])]
    return tuple(best) if best else None


def best_four_of_five_wiring():
    """Exhaustive search over all 4-of-5 wirings of six members (member 0's
    omission fixed to member 1 by symmetry).  Returns the maximum achievable
    lower bound on mean cluster size and the wirings attaining it."""
    best_val, best_wirings = -1.0, []
    for rest in product(*[[j for j in range(6) if j != i] for i in range(1, 6)]):
        omitted = (1,) + rest
        lists = wiring_from_omissions(omitted)
        b = cohesion_bound(lists)
        if b is None:
            continue
        if b[0] > best_val + 1e-9:
            best_val, best_wirings = b[0], [list(omitted)]
        elif abs(b[0] - best_val) < 1e-9:
            best_wirings.append(list(omitted))
    return best_val, best_wirings


def analyse_wiring(omitted):
    lists = wiring_from_omissions(omitted)
    b = cohesion_bound(lists)
    r = coercion_screen(lists)
    return {"omitted": list(omitted), "lists": lists, "minMeanCluster": b[0], "minLargestCluster": b[1],
            "minExtraPeers": b[2], "screenFlags": r["flags"]}
