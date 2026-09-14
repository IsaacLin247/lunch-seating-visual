"""Hard-constraint inputs, occupancy targets and independent chart validation.

Everything that decides whether a chart may be released lives here, so that the
solver, the fallback cache, manual adjustments and the trace validator all use
the same checks:

  * unique placement of every active (present) student,
  * exact occupancy targets per table, each within the physical capacity,
  * eligibility (grade-restricted tables in same-grade rotations),
  * the companion guarantee for every obligated student, using only present,
    eligible listed companions,
  * staff constraints: prohibited pairs never share a table, and placement
    restrictions (allowed tables per student) are respected.

``hard_constraint_key`` fingerprints exactly these inputs.  Meeting history is
deliberately outside the key: it changes the score of a chart but never its
validity, so a cached feasible chart stays reusable across rotations with the
same hard constraints and is merely rescored.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .provenance import fingerprint


class SchedulingConflict(ValueError):
    """The current inputs cannot be scheduled without an explicit decision."""

    def __init__(self, message, conflicts=None):
        super().__init__(message)
        self.conflicts = conflicts or []


@dataclass
class StaffConstraints:
    """Optional administrator constraints, expressed over student indices."""
    prohibited_pairs: set = field(default_factory=set)      # frozenset({a, b}) entries
    allowed_tables: dict = field(default_factory=dict)      # student -> sorted list of table indices
    table_targets: list | None = None                       # explicit occupancy per table, or None

    @classmethod
    def from_dict(cls, data, ids=None):
        """Accept JSON with student IDs or indices; ``ids`` maps IDs to indices."""
        data = data or {}
        index = {sid: k for k, sid in enumerate(ids)} if ids else {}

        def idx(v):
            return index[v] if isinstance(v, str) else int(v)
        pairs = {frozenset((idx(a), idx(b))) for a, b in data.get("prohibitedPairs", [])}
        if any(len(p) != 2 for p in pairs):
            raise ValueError("a prohibited pair must name two distinct students")
        allowed = {idx(k): sorted(int(t) for t in v) for k, v in data.get("allowedTables", {}).items()}
        targets = data.get("tableTargets")
        return cls(prohibited_pairs=pairs, allowed_tables=allowed,
                   table_targets=None if targets is None else [int(t) for t in targets])

    def to_dict(self, ids=None):
        name = (lambda i: ids[i]) if ids else (lambda i: i)
        return {"prohibitedPairs": sorted(sorted(name(m) for m in p) for p in self.prohibited_pairs),
                "allowedTables": {name(k): v for k, v in sorted(self.allowed_tables.items())},
                "tableTargets": self.table_targets}

    def is_empty(self):
        return not self.prohibited_pairs and not self.allowed_tables and self.table_targets is None


EMPTY_STAFF = StaffConstraints()


def occupancy_targets(caps, table_grade, grade, present, explicit=None, min_occupancy=2):
    """Occupancy per table for the present roster, within physical capacities.

    Absences reduce table targets one seat at a time, largest tables first
    within the admissible pool, so that every table stays as full as possible
    and no table drops below ``min_occupancy`` while another could shrink
    instead.  A table can close (target 0) only when the pool is smaller than
    its minimum occupancies allow.  ``explicit`` overrides everything but is
    validated against the same limits.
    """
    caps = list(caps)
    T = len(caps)
    pools = {}
    for i in present:
        pools.setdefault(grade[i] if any(g is not None for g in table_grade) else None, 0)
        pools[grade[i] if any(g is not None for g in table_grade) else None] += 1
    if explicit is not None:
        explicit = list(explicit)
        if len(explicit) != T or any(not 0 <= x <= c for x, c in zip(explicit, caps)):
            raise ValueError("explicit table targets must respect every physical capacity")
        for g, need in pools.items():
            have = sum(x for x, tg in zip(explicit, table_grade) if tg == g)
            if have != need:
                raise ValueError(f"explicit targets seat {have} students of pool {g}, but {need} are present")
        return explicit
    targets = list(caps)
    for g, need in pools.items():
        tables = [t for t in range(T) if table_grade[t] == g]
        capacity = sum(caps[t] for t in tables)
        if need > capacity:
            raise ValueError(f"{need} present students of pool {g} exceed the physical capacity {capacity}")
        surplus = capacity - need
        while surplus > 0:
            # shrink the currently fullest table that can still shrink
            candidates = [t for t in tables if targets[t] > min_occupancy]
            if not candidates:
                candidates = [t for t in tables if targets[t] > 0]
            t = max(candidates, key=lambda t: (targets[t], -t))
            targets[t] -= 1
            surplus -= 1
    return targets


def hard_constraint_key(grade, lists, caps, table_grade, state, present=None, staff=None, targets=None):
    """Fingerprint of every feasibility input; history is intentionally excluded."""
    n = len(grade)
    present = sorted(range(n)) if present is None else sorted(present)
    present_set = set(present)
    staff = staff or EMPTY_STAFF
    payload = {
        "state": state,
        "present": present,
        "grade": [grade[i] for i in present],
        "lists": [[j for j in lists[i] if j in present_set] for i in present],
        "capacities": list(caps),
        "tableGrade": list(table_grade),
        "targets": list(targets) if targets is not None else None,
        "staff": staff.to_dict(),
    }
    return fingerprint(payload)


def validate_chart(p, assign, *, strict=True):
    """Independent hard-constraint check of a full assignment for problem ``p``.

    Returns a report dict; ``report['valid']`` is True only when every check
    passes.  This does not consult the solver's cached bookkeeping.
    """
    report = {"valid": True, "problems": []}

    def fail(kind, **info):
        report["valid"] = False
        report["problems"].append({"kind": kind, **info})
    n, T = p.n, p.T
    if len(assign) != n or any(not isinstance(t, int) or not 0 <= t < T for t in assign):
        fail("placement", detail="every student needs exactly one table index")
        return report
    members = [[] for _ in range(T)]
    for i, t in enumerate(assign):
        members[t].append(i)
    for t in range(T):
        if len(members[t]) != p.targets[t]:
            fail("occupancy", table=t, occupancy=len(members[t]), target=p.targets[t])
        if len(members[t]) > p.caps[t]:
            fail("capacity", table=t, occupancy=len(members[t]), capacity=p.caps[t])
        if p.table_grade[t] is not None:
            for i in members[t]:
                if p.grade[i] != p.table_grade[t]:
                    fail("eligibility", table=t, student=i, grade=p.grade[i], tableGrade=p.table_grade[t])
    for i in range(n):
        if assign[i] not in p.allowed_set[i]:
            fail("placement-restriction", student=i, table=assign[i])
    for i in range(n):
        if p.submitter[i]:
            ms = members[assign[i]]
            if not any(j in p.adj[i] for j in ms if j != i):
                fail("companion", student=i, table=assign[i])
    for pair in p.prohibited_pairs:
        a, b = tuple(pair)
        if assign[a] == assign[b]:
            fail("prohibited-pair", students=sorted((a, b)), table=assign[a])
    return report
