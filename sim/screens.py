"""Pre-solve submission screens.

(a) Insularity screen: a student whose list-closure (follow listed names
    transitively, including themselves) has size 2..12 sits in a small closed
    world -- a coercive kernel that could be used to capture a table.
(b) Boundary screen: clusters of students with heavy pairwise list overlap
    (>= 3 shared names) whose combined *outward* names number <= 3.

Flagged groups are returned to the students for diversification; they are not
seated by the solver until they resubmit.
"""
from __future__ import annotations


def list_closure(lists: list[list[int]], start: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        i = stack.pop()
        for j in lists[i]:
            if j not in seen:
                seen.add(j)
                stack.append(j)
    return seen


def insularity_screen(lists: list[list[int]], min_size: int = 2, max_size: int = 12) -> list[dict]:
    flagged: dict[frozenset, dict] = {}
    for i, lst in enumerate(lists):
        if not lst:
            continue
        cl = list_closure(lists, i)
        if min_size <= len(cl) <= max_size:
            key = frozenset(cl)
            flagged.setdefault(key, {"screen": "insularity", "kernel": sorted(cl), "members": set()})
            flagged[key]["members"].add(i)
    out = []
    for f in flagged.values():
        f["members"] = sorted(f["members"])
        out.append(f)
    return out


def boundary_screen(lists: list[list[int]], min_overlap: int = 3, max_outward: int = 3) -> list[dict]:
    n = len(lists)
    sets = [set(l) for l in lists]
    subs = [i for i in range(n) if sets[i]]
    # union-find over heavy-overlap pairs
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
    comps: dict[int, list[int]] = {}
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


def run_screens(lists: list[list[int]]) -> dict:
    flags = insularity_screen(lists) + boundary_screen(lists)
    flagged_students = sorted({m for f in flags for m in f["members"]})
    return {"flags": flags, "flaggedStudents": flagged_students}
