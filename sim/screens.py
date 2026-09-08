"""Pre-solve submission screens.

Two independent checks are applied to the submitted lists, once per rotation
*state* (mixed, and same-grade with cross-grade names removed), because the
hard guarantee is enforced on the state's effective graph and an attack can hide
inside names that vanish in stratified rounds.

1. Coercion screen (exact on bounded candidates).
   Let D be the effective list digraph.  A set A is *closed* when every
   submitter in A has a listed peer inside A (non-submitters have no
   obligation and never break closedness).  A closed set S is *coercive* when
   it contains at least two submitters and admits no partition S = A (+) B into
   two closed parts that both contain a submitter: every feasible seating then
   keeps all submitters of S at one table (capture if it fits, infeasibility if
   it does not).  Candidates are the list-closures of submitters; they are
   closed by construction.  Candidates of size <= EXACT_LIMIT are decided by
   exhaustive enumeration; larger ones pass when every submitter has at least
   three listed peers inside the set (Thomassen 1983: minimum out-degree three
   gives two disjoint cycles, which extend to two closed parts) and are
   otherwise searched heuristically and flagged as "unverified" if no split is
   found.

2. Demand screen (capacity).
   For a closed candidate C with followers F(C) = submitters outside C whose
   effective list lies entirely inside C: every table touching C (+) F(C) holds
   a member of C, and if that member submitted a list it needs a second member
   of C.  Hence at most  n0 + floor(n1/2)  tables can hold anyone of C (+) F(C),
   where n0/n1 are the non-submitters/submitters in C, and the instance is
   infeasible when |C| + |F(C)| exceeds the seats of that many largest tables.

Passing both screens is *not* a feasibility certificate; feasibility is
certified separately by CP-SAT on the hard constraints (solver.feasibility).
The older detectors insular_screen / boundary_screen are kept for comparison
only; they are not used for flagging because a cluster with outward names is
not forced anywhere (its members can be anchored outside).
"""
from __future__ import annotations

EXACT_LIMIT = 20     # exhaustive closed-bipartition search up to this size
CANDIDATE_CAP = 64   # closures larger than this are the ordinary population


# ---------------------------------------------------------------- basics ------
def effective_lists(lists, grade=None, state="mixed"):
    """Lists as the guarantee sees them in a rotation state."""
    if state == "mixed" or grade is None:
        return [list(l) for l in lists]
    return [[j for j in l if grade[j] == grade[i]] for i, l in enumerate(lists)]


def list_closure(lists, start):
    seen = {start}
    stack = [start]
    while stack:
        i = stack.pop()
        for j in lists[i]:
            if j not in seen:
                seen.add(j)
                stack.append(j)
    return seen


def is_closed(part, lists):
    """Every submitter in `part` keeps a listed peer inside it."""
    part = set(part)
    for m in part:
        if lists[m] and not any(j in part for j in lists[m]):
            return False
    return True


def _submitters(S, lists):
    return [m for m in S if lists[m]]


# ------------------------------------------------ closed bipartitions ---------
def closed_bipartition(S, lists):
    """A split S = A (+) B into closed parts that both contain a submitter, or None.

    Exact for |S| <= EXACT_LIMIT (2^(|S|-1) masks, one submitter pinned to A).
    Above that: returns a split found by the Thomassen construction / greedy
    search, or None if none was found (which is then *not* a proof)."""
    members = sorted(S)
    subs = [m for m in members if lists[m]]
    if len(subs) < 2:
        return None
    if len(members) <= EXACT_LIMIT:
        return _exact_split(members, lists)
    split, proven = _cpsat_split(members, lists)
    return split


def _exact_split(members, lists):
    k = len(members)
    idx = {m: i for i, m in enumerate(members)}
    out = [0] * k
    sub_mask = 0
    for i, m in enumerate(members):
        if lists[m]:
            sub_mask |= 1 << i
            for j in lists[m]:
                if j in idx:
                    out[i] |= 1 << idx[j]
    pin = (sub_mask & -sub_mask).bit_length() - 1     # lowest submitter pinned to A
    full = (1 << k) - 1
    subs = [i for i in range(k) if (sub_mask >> i) & 1]

    def closed(mask):
        for i in subs:
            if (mask >> i) & 1 and not (out[i] & mask):
                return False
        return True

    for half in range(1 << (k - 1)):
        # insert the pinned bit as 1
        a = ((half >> pin) << (pin + 1)) | (1 << pin) | (half & ((1 << pin) - 1))
        b = full ^ a
        if not (b & sub_mask):
            continue
        if closed(a) and closed(b):
            A = [members[i] for i in range(k) if (a >> i) & 1]
            B = [members[i] for i in range(k) if (b >> i) & 1]
            return A, B
    return None


def _cpsat_split(members, lists, time_limit=10.0):
    """Exact closed-bipartition decision for larger candidates via CP-SAT.
    Returns (split or None, proven) where proven=False means the budget expired."""
    from ortools.sat.python import cp_model
    S = set(members)
    subs = [m for m in members if lists[m]]
    model = cp_model.CpModel()
    side = {m: model.NewBoolVar(f"s{m}") for m in members}
    for v in subs:
        same = []
        for j in lists[v]:
            if j not in S:
                continue
            e = model.NewBoolVar(f"e{v}_{j}")
            # e -> side_v == side_j
            model.Add(side[v] - side[j] <= 1 - e)
            model.Add(side[j] - side[v] <= 1 - e)
            same.append(e)
        model.AddBoolOr(same)
    model.Add(side[subs[0]] == 0)
    model.Add(sum(side[v] for v in subs) >= 1)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.max_time_in_seconds = time_limit
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        A = sorted(m for m in members if solver.Value(side[m]) == 0)
        B = sorted(m for m in members if solver.Value(side[m]) == 1)
        assert is_closed(A, lists) and is_closed(B, lists)
        return (A, B), True
    if status == cp_model.INFEASIBLE:
        return None, True
    return None, False


def min_internal_outdegree(S, lists):
    S = set(S)
    degs = [sum(1 for j in lists[m] if j in S) for m in S if lists[m]]
    return min(degs) if degs else 0


# ------------------------------------------------------ candidate sets --------
def closed_candidates(lists, cap=CANDIDATE_CAP):
    """Distinct list-closures of submitters with size <= cap (all closed sets)."""
    seen = {}
    for i, l in enumerate(lists):
        if not l:
            continue
        cl = list_closure(lists, i)
        if len(cl) <= cap:
            key = frozenset(cl)
            seen.setdefault(key, set()).add(i)
    return [(sorted(S), sorted(v)) for S, v in seen.items()]


# ------------------------------------------------------------ screens ---------
def coercion_screen(lists, cap=CANDIDATE_CAP):
    """Coercion verdicts for every closed candidate set of one effective graph."""
    flags, cands = [], []
    for S, seeds in sorted(closed_candidates(lists, cap)):
        subs = _submitters(S, lists)
        c = {"members": S, "submitters": subs, "size": len(S), "seeds": seeds}
        if len(subs) < 2:
            c["flagged"] = False
            c["reason"] = "single submitter"
        elif len(S) <= EXACT_LIMIT:
            split = _exact_split(S, lists)
            c["flagged"] = split is None
            c["exact"] = True
            if split:
                c["split"] = [sorted(split[0]), sorted(split[1])]
        elif min_internal_outdegree(S, lists) >= 3:
            c["flagged"] = False
            c["exact"] = True
            c["reason"] = "minimum internal out-degree >= 3 (Thomassen: two disjoint cycles extend to two closed parts)"
        else:
            split, proven = _cpsat_split(S, lists)
            c["exact"] = proven
            c["flagged"] = split is None
            if split:
                c["split"] = [sorted(split[0]), sorted(split[1])]
            elif proven:
                c["reason"] = "no closed bipartition (CP-SAT proof)"
            else:
                c["reason"] = "no split found within the time budget (unverified)"
        cands.append(c)
        if c["flagged"]:
            flags.append({"screen": "coercion", "members": S, "submitters": subs, "size": len(S),
                          "exact": c.get("exact", True)})
    return {"flags": flags, "candidates": cands}


def demand_screen(lists, caps, cap=CANDIDATE_CAP):
    """Capacity check for closed cores with followers (see module docstring)."""
    caps_sorted = sorted(caps, reverse=True)
    flags = []
    for S, _seeds in sorted(closed_candidates(lists, cap)):
        Sset = set(S)
        n1 = sum(1 for m in S if lists[m])
        n0 = len(S) - n1
        followers = [i for i, l in enumerate(lists) if l and i not in Sset and set(l) <= Sset]
        max_tables = n0 + n1 // 2
        seats = sum(caps_sorted[:max_tables])
        demand = len(S) + len(followers)
        if demand > seats:
            flags.append({"screen": "demand", "core": S, "followers": followers, "demand": demand,
                          "maxTables": max_tables, "seats": seats})
    return flags


def min4_violations(lists, min_list=4):
    return [i for i, l in enumerate(lists) if 0 < len(l) < min_list]


def same_grade_violations(lists, grade, min_same=2):
    return [i for i, l in enumerate(lists) if l and sum(1 for j in l if grade[j] == grade[i]) < min_same]


def run_screens(lists, grade=None, caps_by_state=None, states=None):
    """Apply both screens on every rotation state's effective graph.

    Returns per-state candidates and flags plus the union of flagged and
    returned students.  ``returnedStudents`` are the submitters of every
    flagged coercive set and the core submitters and followers of every
    over-demanded core."""
    if states is None:
        states = ("mixed", "same") if grade is not None else ("mixed",)
    per_state, flagged, returned = {}, set(), set()
    for state in states:
        eff = effective_lists(lists, grade, state)
        co = coercion_screen(eff)
        caps = (caps_by_state or {}).get(state)
        dem = demand_screen(eff, caps) if caps else []
        ineligible = [i for i, (l, e) in enumerate(zip(lists, eff)) if l and not e]
        per_state[state] = {"candidates": co["candidates"], "flags": co["flags"], "demandFlags": dem,
                            "ineligible": ineligible}
        for f in co["flags"]:
            flagged.update(f["submitters"])
            returned.update(f["submitters"])
        for f in dem:
            flagged.update(m for m in f["core"] if lists[m])
            returned.update(m for m in f["core"] if lists[m])
            returned.update(f["followers"])
    return {"rule": "coercion+demand on effective graphs", "states": list(states), "perState": per_state,
            "flags": [dict(f, state=s) for s in states for f in per_state[s]["flags"]],
            "demandFlags": [dict(f, state=s) for s in states for f in per_state[s]["demandFlags"]],
            "flaggedStudents": sorted(flagged), "returnedStudents": sorted(returned),
            "min4Violations": min4_violations(lists),
            "sameGradeViolations": same_grade_violations(lists, grade) if grade is not None else [],
            "ineligible": sorted({i for s in states for i in per_state[s]["ineligible"]})}


# ------------------------------------------- legacy detectors (diagnostic) ----
def insular_screen(lists, min_size=2, max_size=12):
    """Small closed worlds under list-following (diagnostic only)."""
    flagged = {}
    for i, lst in enumerate(lists):
        if not lst:
            continue
        cl = list_closure(lists, i)
        if min_size <= len(cl) <= max_size:
            key = frozenset(cl)
            flagged.setdefault(key, {"screen": "insular", "kernel": sorted(cl), "members": set()})
            flagged[key]["members"].add(i)
    out = []
    for f in flagged.values():
        f["members"] = sorted(f["members"])
        out.append(f)
    return out


insularity_screen = insular_screen


def boundary_screen(lists, min_overlap=3, max_outward=3):
    """Heavy pairwise list overlap with few outward names (diagnostic only)."""
    n = len(lists)
    sets = [set(l) for l in lists]
    subs = [i for i in range(n) if sets[i]]
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for ai, a in enumerate(subs):
        for b in subs[ai + 1:]:
            if len(sets[a] & sets[b]) >= min_overlap:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
    comps = {}
    for a in subs:
        comps.setdefault(find(a), []).append(a)
    out = []
    for comp in comps.values():
        if len(comp) < 2:
            continue
        cs = set(comp)
        outward = set().union(*(sets[c] for c in comp)) - cs
        if len(outward) <= max_outward:
            out.append({"screen": "boundary", "members": sorted(comp), "outward": len(outward)})
    return out
