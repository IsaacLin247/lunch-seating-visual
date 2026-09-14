"""Pre-solve submission screens.

Two independent checks are applied to the submitted lists, once per rotation
*state* (mixed, and same-grade with cross-grade names removed), because the
hard guarantee is enforced on the state's effective graph and an attack can hide
inside names that vanish in stratified rounds.

1. Coercion screen (sound proofs on bounded candidates, incomplete coverage).
   Let D be the effective list digraph.  A set A is *closed* when every
   submitter in A has a listed peer inside A (non-submitters have no
   obligation and never break closedness). A successor-closed set S (every
   listed name of its members also belongs to S) is *coercive* when
   it contains at least two submitters and admits no partition S = A (+) B into
   two closed parts that both contain a submitter: every feasible seating then
   keeps all submitters of S at one table (capture if it fits, infeasibility if
   it does not). Candidates are the reachable list-closures of submitters;
   they are successor-closed by construction. Merely keeping one internal
   name does not suffice for this implication. Candidates of size <= EXACT_LIMIT are decided by
   exhaustive enumeration; larger sets containing only submitters pass when
   minimum distinct internal out-degree is at least three (Thomassen 1983).
   Other larger sets use a deterministic-budget CP-SAT decision. UNKNOWN is
   unresolved, never a proof or an automatic return.

   Small strongly connected cores, including those exposed by deleting one
   possible anchor, are also examined. Retain all core lists and their named
   outside anchors, but remove the outside anchors' obligations. If even this
   relaxation has no closed bipartition separating core members, every real
   feasible chart keeps the core together. A split only clears this necessary
   test; it is not a valid full-population seating certificate.

2. Demand screen (capacity).
   For a successor-closed candidate C with followers F(C) = submitters outside C whose
   effective list lies entirely inside C: every table touching C (+) F(C) holds
   a member of C, and if that member submitted a list it needs a second member
   of C.  Hence at most  n0 + floor(n1/2)  tables can hold anyone of C (+) F(C),
   where n0/n1 are the non-submitters/submitters in C, and the instance is
   infeasible when |C| + |F(C)| exceeds the seats of that many largest
   grade-admissible tables. Same-grade checks require grade-specific pools.

Passing both screens is *not* a feasibility certificate; feasibility is
certified separately by CP-SAT on the hard constraints (solver.feasibility).
The older detectors insular_screen / boundary_screen are diagnostic only.
Outside names can themselves force a group together; candidate coverage is
explicitly bounded and these screens are not a complete anti-capture test.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

EXACT_LIMIT = 20     # exhaustive closed-bipartition search up to this size
CANDIDATE_CAP = 64   # larger reachable closures are omitted, not proved safe
TARGET_CORE_CAP = 12
TARGET_CANDIDATE_LIMIT = 256
SCREEN_DETERMINISTIC_TIME = 10.0  # per CP-SAT candidate; not wall-clock seconds
SEPARATION_DETERMINISTIC_TIME = 10.0   # per full-model separation test
FULL_MODEL_CANDIDATE_LIMIT = 32        # full-model tests per state (budgeted, reported)
FULL_MODEL_GROUP_CAP = 12              # largest group tested with the full model


@dataclass(frozen=True)
class ScreenBudget:
    """Configurable screening budgets; every limit is reported as coverage."""
    closure_cap: int = CANDIDATE_CAP
    exact_limit: int = EXACT_LIMIT
    target_core_cap: int = TARGET_CORE_CAP
    target_candidate_limit: int = TARGET_CANDIDATE_LIMIT
    deterministic_time: float = SCREEN_DETERMINISTIC_TIME
    separation_time: float = SEPARATION_DETERMINISTIC_TIME
    full_model_limit: int = FULL_MODEL_CANDIDATE_LIMIT
    full_model_group_cap: int = FULL_MODEL_GROUP_CAP
    full_model_policy: str = "risk"     # "risk" (flagged, unresolved, anchor-exposed cores), "all", "none"
    workers: int = 1

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


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
    Above that: returns a CP-SAT witness, or None. This convenience function
    does not distinguish a proof from UNKNOWN; use coercion_screen for verdicts.
    """
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


def _cpsat_split(members, lists, time_limit=SCREEN_DETERMINISTIC_TIME):
    """Exact closed-bipartition decision for larger candidates via CP-SAT.
    Returns (split or None, proven) where proven=False means unresolved.
    ``time_limit`` is deterministic solver time, retained as a compatibility
    parameter name; no wall-clock deadline is imposed.
    """
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
    solver.parameters.max_deterministic_time = time_limit
    solver.parameters.random_seed = 0
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
    degs = [len(set(lists[m]) & S) for m in S if lists[m]]
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


def _strong_components(lists, excluded=None):
    """Deterministic iterative Kosaraju decomposition, omitting one anchor."""
    vertices = [i for i in range(len(lists)) if i != excluded]
    adj = {i: sorted(set(lists[i]) - {excluded}) for i in vertices}
    reverse = {i: [] for i in vertices}
    for i in vertices:
        for j in adj[i]:
            reverse[j].append(i)
    seen, order = set(), []
    for start in vertices:
        if start in seen:
            continue
        seen.add(start)
        stack = [(start, iter(adj[start]))]
        while stack:
            v, edges = stack[-1]
            j = next(edges, None)
            if j is None:
                order.append(v)
                stack.pop()
            elif j not in seen:
                seen.add(j)
                stack.append((j, iter(adj[j])))
    seen.clear()
    for start in reversed(order):
        if start in seen:
            continue
        component, stack = [], [start]
        seen.add(start)
        while stack:
            v = stack.pop()
            component.append(v)
            for j in reverse[v]:
                if j not in seen:
                    seen.add(j)
                    stack.append(j)
        yield sorted(component)


def targeted_candidates(lists, core_cap=TARGET_CORE_CAP, limit=TARGET_CANDIDATE_LIMIT):
    """Small SCC cores in the graph and after deleting each single vertex.

    Deletion is only a candidate-generation device: the decision test restores
    every named outside anchor. No list edge is discarded from a core's
    obligation. Candidates are deduplicated, then ordered by size and IDs.
    The reported count and truncation make this incomplete coverage explicit.
    """
    found, original_cores = {}, set()
    for omitted in [None, *range(len(lists))]:
        for core in _strong_components(lists, omitted):
            if 2 <= len(core) <= core_cap:
                key = tuple(core)
                if omitted is None:
                    original_cores.add(key)
                    found.setdefault(key, [])
                elif key not in original_cores:
                    found.setdefault(key, []).append(omitted)
    ordered = sorted(found, key=lambda core: (len(core), core))
    return ([{"core": list(core), "anchorDeletions": sorted(set(found[core]))}
             for core in ordered[:limit]], len(ordered))


def _decide_candidate(candidate, members, decision_lists, deterministic_time, allow_degree_shortcut=False,
                      exact_limit=EXACT_LIMIT):
    """Attach a three-way verdict. Only a proof can set ``flagged``."""
    subs = _submitters(members, decision_lists)
    split, proven = None, True
    if len(subs) < 2:
        candidate.update(verdict="proved-pass", flagged=False, exact=True,
                         reason="fewer than two obligated core members")
        return candidate
    if len(members) <= exact_limit:
        split = _exact_split(members, decision_lists)
        reason = "exhaustive closed-bipartition decision"
    elif (allow_degree_shortcut and len(subs) == len(members)
          and min_internal_outdegree(members, decision_lists) >= 3):
        # The cited minimum-out-degree theorem applies to ALL vertices. Do not
        # apply it to a relaxed graph whose outside anchors have no obligation.
        candidate.update(verdict="proved-pass", flagged=False, exact=True,
                         reason="minimum internal out-degree >= 3 on all vertices (Thomassen)")
        return candidate
    else:
        split, proven = _cpsat_split(members, decision_lists, time_limit=deterministic_time)
        reason = ("closed-bipartition CP-SAT proof" if proven else
                  "no decision within deterministic budget; review or retry required")
    verdict = "proved-pass" if split else ("proved-coercive" if proven else "unresolved")
    candidate.update(verdict=verdict, flagged=verdict == "proved-coercive",
                     exact=proven, reason=reason)
    if split:
        candidate["split"] = [sorted(split[0]), sorted(split[1])]
    return candidate


# ------------------------------------------------------------ screens ---------
def coercion_screen(lists, cap=CANDIDATE_CAP, deterministic_time=SCREEN_DETERMINISTIC_TIME,
                    target_core_cap=TARGET_CORE_CAP, target_limit=TARGET_CANDIDATE_LIMIT,
                    exact_limit=EXACT_LIMIT):
    """Sound forcing certificates for bounded candidates of one effective graph.

    ``proved-pass`` means only that the candidate passed its stated necessary
    test. ``unresolved`` never enters flags or returnedStudents. Candidate
    generation is incomplete even when every examined test is decided.
    """
    flags, cands = [], []
    for S, seeds in sorted(closed_candidates(lists, cap)):
        subs = _submitters(S, lists)
        c = {"kind": "list-closure", "members": S, "core": subs,
             "outside": sorted(set(S) - set(subs)), "submitters": subs,
             "size": len(S), "seeds": seeds, "relaxationMembers": S}
        _decide_candidate(c, S, lists, deterministic_time, allow_degree_shortcut=True, exact_limit=exact_limit)
        cands.append(c)
        if c["flagged"]:
            flags.append(dict(c, screen="coercion"))

    targeted, discovered = targeted_candidates(lists, target_core_cap, target_limit)
    examined = 0
    for target in targeted:
        core = target["core"]
        core_set = set(core)
        # Closed cores were already tested above; subsets of a certified
        # forced group need no redundant certificate or additional return.
        outside = sorted(set().union(*(set(lists[i]) for i in core)) - core_set)
        if (not outside and len(core) <= cap) or any(core_set <= set(f["submitters"]) for f in flags):
            continue
        relaxed = [list(lists[i]) if i in core_set else [] for i in range(len(lists))]
        members = sorted(core + outside)
        c = {"kind": "targeted-core", "members": core, "core": core,
             "outside": outside, "submitters": core, "size": len(core),
             "seeds": [], "anchorDeletions": target["anchorDeletions"],
             "relaxationMembers": members}
        _decide_candidate(c, members, relaxed, deterministic_time, exact_limit=exact_limit)
        cands.append(c)
        examined += 1
        if c["flagged"]:
            flags.append(dict(c, screen="targeted-coercion"))
    return {"flags": flags, "candidates": cands,
            "unresolvedCandidates": [c for c in cands if c["verdict"] == "unresolved"],
            "coverage": {"complete": False, "closureSizeCap": cap,
                         "exactEnumerationLimit": exact_limit,
                         "targetCoreSizeCap": target_core_cap, "targetCandidateLimit": target_limit,
                         "targetCandidatesDiscovered": discovered, "targetCandidatesExamined": examined,
                         "targetCandidatesTruncated": discovered > target_limit,
                         "cpDeterministicTimePerCandidate": deterministic_time}}


def demand_screen(lists, caps, cap=CANDIDATE_CAP, grade=None, caps_by_grade=None):
    """Capacity check using the pool actually admissible to each closed core.

    When ``caps_by_grade`` is given, all members of a core and its followers
    must have a single grade; other cases are rejected as configuration errors.
    Mixed-state callers use ``caps``. Same-state callers supply both ``grade``
    and ``caps_by_grade``; a missing grade pool is an error, never borrowed seats.
    """
    flags = []
    for S, _seeds in sorted(closed_candidates(lists, cap)):
        Sset = set(S)
        n1 = sum(1 for m in S if lists[m])
        n0 = len(S) - n1
        followers = [i for i, l in enumerate(lists) if l and i not in Sset and set(l) <= Sset]
        eligible_grade = None
        if caps_by_grade is not None:
            if grade is None:
                raise ValueError("grade is required with grade-specific capacity pools")
            groups = {grade[i] for i in S + followers}
            if len(groups) != 1:
                raise ValueError("a same-grade demand core spans multiple grades")
            eligible_grade = next(iter(groups))
            # JSON-loaded capacity maps may have string keys.
            pool = caps_by_grade.get(eligible_grade, caps_by_grade.get(str(eligible_grade)))
            if pool is None:
                raise ValueError(f"missing capacity pool for grade {eligible_grade}")
        else:
            pool = caps
        caps_sorted = sorted(pool, reverse=True)
        max_tables = n0 + n1 // 2
        seats = sum(caps_sorted[:max_tables])
        demand = len(S) + len(followers)
        if demand > seats:
            flags.append({"screen": "demand", "core": S, "followers": followers, "demand": demand,
                          "maxTables": max_tables, "seats": seats,
                          "admissibleGrade": eligible_grade})
    return flags


def min4_violations(lists, min_list=4):
    return [i for i, l in enumerate(lists) if 0 < len(l) < min_list]


def same_grade_violations(lists, grade, min_same=2):
    return [i for i, l in enumerate(lists) if l and sum(1 for j in l if grade[j] == grade[i]) < min_same]


def run_screens(lists, grade=None, caps_by_state=None, states=None,
                caps_by_grade_by_state=None, deterministic_time=SCREEN_DETERMINISTIC_TIME, budget=None):
    """Apply both screens on every rotation state's effective graph.

    Returns per-state candidates and flags plus the union of flagged and
    returned students.  ``returnedStudents`` are the submitters of every
    proved coercive core and the core submitters and followers of every
    over-demanded core. Outside anchors of a targeted core are never returned
    merely because they appeared in that proof. Unresolved candidates/checks
    are reported separately. Same-grade demand requires
    ``caps_by_grade_by_state={"same": {grade: capacities}}``.
    """
    if states is None:
        states = ("mixed", "same") if grade is not None else ("mixed",)
    budget = ScreenBudget.from_dict(budget) if budget is not None else ScreenBudget(deterministic_time=deterministic_time)
    per_state, flagged, returned, unresolved_checks = {}, set(), set(), []
    for state in states:
        eff = effective_lists(lists, grade, state)
        co = coercion_screen(eff, cap=budget.closure_cap, deterministic_time=budget.deterministic_time,
                             target_core_cap=budget.target_core_cap, target_limit=budget.target_candidate_limit,
                             exact_limit=budget.exact_limit)
        caps = (caps_by_state or {}).get(state)
        grade_caps = (caps_by_grade_by_state or {}).get(state)
        if state != "mixed" and grade is not None and caps is not None and grade_caps is None:
            dem, demand_status = [], "unresolved"
            unresolved_checks.append({"state": state, "screen": "demand",
                                      "reason": "grade-specific admissible capacity pools were not supplied"})
        elif caps is not None or grade_caps is not None:
            dem = demand_screen(eff, caps, cap=budget.closure_cap, grade=grade, caps_by_grade=grade_caps)
            demand_status = "checked"
        else:
            dem, demand_status = [], "not-requested"
        ineligible = [i for i, (l, e) in enumerate(zip(lists, eff)) if l and not e]
        per_state[state] = {"candidates": co["candidates"], "flags": co["flags"], "demandFlags": dem,
                            "ineligible": ineligible, "demandStatus": demand_status,
                            "unresolvedCandidates": co["unresolvedCandidates"], "coverage": co["coverage"]}
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
            "unresolvedCandidates": [dict(c, state=s) for s in states for c in per_state[s]["unresolvedCandidates"]],
            "unresolvedChecks": unresolved_checks,
            "flaggedStudents": sorted(flagged), "returnedStudents": sorted(returned),
            "min4Violations": min4_violations(lists),
            "sameGradeViolations": same_grade_violations(lists, grade) if grade is not None else [],
            "ineligible": sorted({i for s in states for i in per_state[s]["ineligible"]}),
            "budget": budget.to_dict()}


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


# ------------------------------------------- full-model separation test ------
def separation_test(p, group, *, time_limit=SEPARATION_DETERMINISTIC_TIME, workers=1, seed=0,
                    deterministic=True, base_status=None):
    """Can the group be split across at least two tables in some valid chart?

    Uses the complete assignment model of problem ``p`` (occupancy targets,
    eligibility, attendance-restricted lists, every companion obligation, and
    staff constraints) plus, for every table t,  sum_{i in C} x[i,t] <= |C|-1.

    Verdicts:
      separable   FEASIBLE/OPTIMAL; the returned witness chart is validated
                  independently and really seats the group at >= 2 tables
      forced      INFEASIBLE: no valid chart under the current full constraints
                  separates the group (vacuous only if the base is infeasible,
                  which is why the base status is established first)
      unresolved  UNKNOWN within the deterministic budget
    """
    from ortools.sat.python import cp_model
    from .constraints import validate_chart
    from .solver import _base_model, _cpsat_solver, _extract, feasibility_certificate, InfeasibleInputError
    group = sorted(set(group))
    result = {"group": group, "size": len(group), "deterministicTime": time_limit, "workers": workers}
    if len(group) < 2:
        result.update(verdict="trivial", reason="fewer than two members")
        return result
    if base_status is None:
        try:
            base_status, _ = feasibility_certificate(p, time_limit=time_limit, workers=workers, seed=seed,
                                                     deterministic=deterministic)
        except InfeasibleInputError as exc:
            base_status = f"INFEASIBLE_INPUT: {exc}"
    result["baseStatus"] = base_status
    if base_status.startswith("INFEASIBLE"):
        result.update(verdict="base-infeasible", reason="the instance itself admits no valid chart; separation is undefined")
        return result
    model, x, _ = _base_model(p)
    for t in range(p.T):
        at_t = [x[i, t] for i in group if (i, t) in x]
        if at_t:
            model.Add(sum(at_t) <= len(group) - 1)
    solver = _cpsat_solver(time_limit, workers, seed, deterministic)
    status = solver.Solve(model)
    name = solver.StatusName(status)
    result["status"] = name
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assign = _extract(p, x, solver)
        report = validate_chart(p, assign)
        tables = {assign[i] for i in group}
        if not report["valid"] or len(tables) < 2:
            raise AssertionError("separation witness failed independent validation")
        result.update(verdict="separable", witness=assign, witnessTables=sorted(tables),
                      reason="a validated chart seats the group at two or more tables")
    elif status == cp_model.INFEASIBLE:
        result.update(verdict="forced",
                      reason="no valid chart under the current full constraints separates this group"
                             + ("" if base_status in ("OPTIMAL", "FEASIBLE") else
                                " (base feasibility is not certified, so this may also reflect global infeasibility)"))
    else:
        result.update(verdict="unresolved", reason="no decision within the deterministic budget")
    return result


def _risk_rank(candidate):
    """Order candidates for the budgeted full-model test: unresolved and flagged
    first, then anchor-exposed targeted cores, then small closures."""
    verdict = candidate.get("verdict")
    exposed = len(candidate.get("anchorDeletions", []) or [])
    return (0 if verdict == "unresolved" else 1 if verdict == "proved-coercive" else 2 if exposed else 3,
            -exposed, candidate.get("size", 0), tuple(candidate.get("core") or candidate.get("members") or []))


def full_model_screen(p, screen_state, *, budget: ScreenBudget | None = None, seed=0, deterministic=True,
                      base_status=None, groups=None):
    """Budgeted full-model separation tests for one rotation state.

    ``screen_state`` is the per-state report of ``run_screens``; ``groups`` are
    optional explicit suspected groups (tested first).  Returns verdicts and
    coverage: how many candidates were discovered, examined, and skipped.
    """
    budget = ScreenBudget.from_dict(budget)
    from .solver import feasibility_certificate, InfeasibleInputError
    if base_status is None:
        try:
            base_status, _ = feasibility_certificate(p, time_limit=budget.separation_time, workers=budget.workers,
                                                     seed=seed, deterministic=deterministic)
        except InfeasibleInputError as exc:
            base_status = f"INFEASIBLE_INPUT: {exc}"
    candidates = []
    seen = set()
    for g in groups or []:
        key = tuple(sorted(set(g)))
        if 2 <= len(key) <= budget.full_model_group_cap and key not in seen:
            seen.add(key)
            candidates.append({"group": list(key), "origin": "supplied", "verdictBefore": None, "size": len(key)})
    ranked = sorted(screen_state.get("candidates", []), key=_risk_rank)
    for c in ranked:
        core = c.get("core") or c.get("submitters") or c.get("members")
        key = tuple(sorted(set(core)))
        if not 2 <= len(key) <= budget.full_model_group_cap or key in seen:
            continue
        if budget.full_model_policy == "none":
            continue
        risky = c.get("verdict") in ("unresolved", "proved-coercive") or bool(c.get("anchorDeletions"))
        if budget.full_model_policy == "risk" and not risky:
            continue
        seen.add(key)
        candidates.append({"group": list(key), "origin": c.get("kind", "screen"), "verdictBefore": c.get("verdict"),
                           "size": len(key)})
    results = []
    examined = 0
    for cand in candidates:
        if examined >= budget.full_model_limit:
            cand["verdict"] = "skipped"
            cand["reason"] = "full-model candidate budget exhausted"
            results.append(cand)
            continue
        outcome = separation_test(p, cand["group"], time_limit=budget.separation_time, workers=budget.workers,
                                  seed=seed, deterministic=deterministic, base_status=base_status)
        examined += 1
        results.append({**cand, **{k: v for k, v in outcome.items() if k != "group"}})
    verdicts = {}
    for r in results:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
    return {"baseStatus": base_status, "results": results, "verdictCounts": verdicts,
            "coverage": {"policy": budget.full_model_policy, "candidatesDiscovered": len(candidates),
                         "candidatesExamined": examined, "candidatesSkipped": len(candidates) - examined,
                         "groupSizeCap": budget.full_model_group_cap, "limit": budget.full_model_limit,
                         "deterministicTimePerTest": budget.separation_time,
                         "complete": False,
                         "note": "Only the listed candidate groups were tested; a forced verdict is a certificate for that group under the current full constraints, and separability of tested groups is not a general anti-capture guarantee."}}
