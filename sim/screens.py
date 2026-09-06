"""Pre-solve submission screens.

Flagging rule used by the scenarios (and stated on Tab 4): coercion_screen.

Candidate sets S come from two cheap detectors, kept for comparison:
  insular_screen   a student whose list-closure (follow listed names
                   transitively, including themselves) has size 2..12
  boundary_screen  clusters of students with heavy pairwise list overlap
                   (>= 3 shared names) whose combined outward names number <= 3

coercion_screen then flags a candidate S exactly when S admits NO bipartition
S = A (+) B with |A|, |B| >= 2 and both parts closed, where a part is closed
when every member has at least one listed peer inside it.  Such an S cannot be
split by any seating, so the hard guarantee would drag all of S onto one table
(or make the rotation infeasible).  |S| <= 12, so exact enumeration over the
2^|S| bipartitions is trivial; we short-circuit on the first valid split.

Flagged groups are returned to the students for diversification.
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


def insular_screen(lists: list[list[int]], min_size: int = 2, max_size: int = 12) -> list[dict]:
    """Insular kernels: small closed worlds under list-following."""
    flagged: dict[frozenset, dict] = {}
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


insularity_screen = insular_screen  # older name


def boundary_screen(lists: list[list[int]], min_overlap: int = 3, max_outward: int = 3) -> list[dict]:
    """Clusters with heavy pairwise list overlap and almost no outward names."""
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


def is_closed(part: set[int], lists: list[list[int]]) -> bool:
    """A part is closed when every member has >= 1 listed peer inside it."""
    for m in part:
        if not any(j in part for j in lists[m]):
            return False
    return True


def closed_bipartition(S: list[int], lists: list[list[int]]) -> tuple[list[int], list[int]] | None:
    """First split S = A (+) B with |A|, |B| >= 2 and both parts closed, else None.

    Exact enumeration over 2^(|S|-1) subsets (member S[0] is pinned to A)."""
    members = sorted(S)
    k = len(members)
    if k < 4:
        return None
    sets = [set(lists[m]) for m in members]
    for mask in range(1, 1 << (k - 1)):
        bits = (mask << 1) | 1                      # S[0] always in A
        size_a = bin(bits).count("1")
        if size_a < 2 or k - size_a < 2:
            continue
        # closed check on the bitmask
        ok = True
        for idx in range(k):
            in_a = (bits >> idx) & 1
            found = False
            for jdx in range(k):
                if jdx != idx and ((bits >> jdx) & 1) == in_a and members[jdx] in sets[idx]:
                    found = True
                    break
            if not found:
                ok = False
                break
        if ok:
            A = [members[i] for i in range(k) if (bits >> i) & 1]
            B = [members[i] for i in range(k) if not (bits >> i) & 1]
            return A, B
    return None


def coercion_screen(submitted: list[list[int]], max_kernel: int = 12) -> dict:
    """Exact coercion-capability screen.

    Returns {"flags": [...], "candidates": [...]} where each candidate records
    the set S, how it was detected, and either the split that clears it or the
    verdict that no closed bipartition exists (flagged)."""
    candidates: dict[frozenset, dict] = {}
    for f in insular_screen(submitted, max_size=max_kernel):
        S = frozenset(f["kernel"])
        candidates.setdefault(S, {"members": sorted(S), "sources": []})["sources"].append("insular")
    for f in boundary_screen(submitted):
        if len(f["members"]) > max_kernel:
            continue
        S = frozenset(f["members"])
        candidates.setdefault(S, {"members": sorted(S), "sources": []})["sources"].append("boundary")
    flags, cands = [], []
    for S, c in sorted(candidates.items(), key=lambda kv: kv[1]["members"]):
        split = closed_bipartition(c["members"], submitted)
        c["size"] = len(S)
        if split is None:
            c["flagged"] = True
            flags.append({"screen": "coercion", "members": c["members"], "size": len(S), "sources": c["sources"]})
        else:
            c["flagged"] = False
            c["split"] = [sorted(split[0]), sorted(split[1])]
        cands.append(c)
    return {"flags": flags, "candidates": cands}


def min4_violations(submitted: list[list[int]], min_list: int = 4) -> list[int]:
    """Students who submitted something but fewer than min_list names."""
    return [i for i, l in enumerate(submitted) if 0 < len(l) < min_list]


def run_screens(lists: list[list[int]]) -> dict:
    """Apply the flagging rule.  ``flaggedStudents`` are members of a flagged
    set; ``returnedStudents`` additionally include every member of a candidate
    kernel that contains a flagged student (the whole group is asked to
    diversify, not just the coercive core)."""
    r = coercion_screen(lists)
    flagged = {m for f in r["flags"] for m in f["members"]}
    returned = set(flagged)
    for c in r["candidates"]:
        if flagged & set(c["members"]):
            returned |= set(c["members"])
    return {"flags": r["flags"], "candidates": r["candidates"], "flaggedStudents": sorted(flagged),
            "returnedStudents": sorted(returned), "min4Violations": min4_violations(lists)}
