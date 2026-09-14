"""Attendance-aware rotation inputs.

A rotation schedules the *active roster*: students present that day.  Listed
companions who are absent (or ineligible in the state) cannot satisfy an
obligation.  A present obligated student whose every listed companion is
absent or ineligible is an explicit conflict that an administrator must
resolve for that rotation; the obligation is never dropped silently.

The solver works over a compact index space of present students; this module
builds the restricted inputs and maps results back to roster indices.
"""
from __future__ import annotations

import random

from .constraints import StaffConstraints, occupancy_targets


def sample_absences(n, rate, seed, rotation):
    """Deterministic synthetic absences: each student absent with probability ``rate``."""
    if rate <= 0:
        return []
    rng = random.Random(f"absence-{seed}-{rotation}")
    return [i for i in range(n) if rng.random() < rate]


def companion_conflicts(lists, grade, state, present, waivers=None):
    """Present obligated students with no present, eligible listed companion."""
    present_set = set(present)
    waivers = waivers or {}
    out = []
    for i in present:
        if not lists[i] or i in waivers:
            continue
        eligible = [j for j in lists[i] if state == "mixed" or grade[j] == grade[i]]
        available = [j for j in eligible if j in present_set]
        if not available:
            out.append({"student": i, "listed": list(lists[i]),
                        "absentListed": [j for j in eligible if j not in present_set],
                        "ineligibleListed": [j for j in lists[i] if j not in eligible],
                        "resolution": "obligation waiver for this rotation, a reviewed list change, or a change of attendance"})
    return out


class RotationRoster:
    """Compact inputs for one rotation over the present students."""

    def __init__(self, grade, lists, caps, table_grade, state, *, absent=(), waivers=None, staff=None,
                 targets=None, min_occupancy=2):
        n = len(grade)
        absent = sorted(set(absent))
        self.n_full = n
        self.absent = absent
        self.present = [i for i in range(n) if i not in set(absent)]
        self.index = {i: k for k, i in enumerate(self.present)}
        self.state = state
        self.waivers = dict(waivers or {})
        present_set = set(self.present)
        self.conflicts = companion_conflicts(lists, grade, state, self.present, self.waivers)
        self.grade = [grade[i] for i in self.present]
        self.lists = []
        for i in self.present:
            if i in self.waivers:
                self.lists.append([])
            else:
                self.lists.append([self.index[j] for j in lists[i] if j in present_set])
        staff = staff or StaffConstraints()
        pairs = {frozenset(self.index[m] for m in pair) for pair in staff.prohibited_pairs
                 if all(m in present_set for m in pair)}
        allowed = {self.index[i]: tables for i, tables in staff.allowed_tables.items() if i in present_set}
        self.staff = StaffConstraints(prohibited_pairs=pairs, allowed_tables=allowed, table_targets=None)
        self.caps = list(caps)
        self.table_grade = list(table_grade)
        explicit = targets if targets is not None else staff.table_targets
        self.targets = occupancy_targets(caps, table_grade, grade, self.present, explicit, min_occupancy)

    def restrict_matrix(self, M):
        return [[M[a][b] for b in self.present] for a in self.present]

    def restrict_tables(self, tables):
        if tables is None:
            return None
        return [[self.index[i] for i in tbl if i in self.index] for tbl in tables]

    def expand(self, assign):
        """Map a compact assignment back to roster indices (absent -> None)."""
        out = [None] * self.n_full
        for k, i in enumerate(self.present):
            out[i] = assign[k]
        return out

    def describe(self, ids=None):
        name = (lambda i: ids[i]) if ids else (lambda i: i)
        return {"present": len(self.present), "absent": [name(i) for i in self.absent],
                "waivedObligations": {name(i): reason for i, reason in sorted(self.waivers.items())},
                "targets": self.targets, "closedTables": [t for t, x in enumerate(self.targets) if x == 0],
                "conflicts": [{**c, "student": name(c["student"]), "listed": [name(j) for j in c["listed"]],
                               "absentListed": [name(j) for j in c["absentListed"]],
                               "ineligibleListed": [name(j) for j in c["ineligibleListed"]]} for c in self.conflicts]}
