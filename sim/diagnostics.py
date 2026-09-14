"""Cross-rotation diagnostics: recurring co-seated groups.

Groups of students that share a table in many rotations are reported for
administrator attention.  Recurring co-seating can result from sincere,
concentrated preferences, from structurally forced cores, from small eligible
pools, or from chance; this report is descriptive and is never a claim about
intent or dishonesty.  Random-baseline charts are analysed with the same rule so
the comparison is like for like.
"""
from __future__ import annotations

from itertools import combinations
from math import ceil


def recurring_groups(tables_by_rotation, *, min_size=4, max_size=5, min_rotations=None):
    """Subsets of ``min_size``..``max_size`` students sharing a table in at least
    ``min_rotations`` rotations (default: half of the rotations, rounded up).

    Returns maximal groups (subsets contained in a reported larger group with
    the same rotation set are dropped), ordered by size and frequency.
    """
    R = len(tables_by_rotation)
    if R == 0:
        return {"threshold": 0, "groups": [], "rotations": 0}
    threshold = ceil(R / 2) if min_rotations is None else min_rotations
    counts = {}
    for r, tables in enumerate(tables_by_rotation):
        for tbl in tables:
            members = sorted(tbl)
            for k in range(min_size, min(max_size, len(members)) + 1):
                for sub in combinations(members, k):
                    counts.setdefault(sub, []).append(r + 1)
    found = {sub: rots for sub, rots in counts.items() if len(rots) >= threshold}
    maximal = []
    for sub in sorted(found, key=lambda s: (-len(s), -len(found[s]), s)):
        rots = found[sub]
        if any(set(sub) < set(big["members"]) and set(rots) <= set(big["rotations"]) for big in maximal):
            continue
        maximal.append({"members": list(sub), "size": len(sub), "rotations": rots,
                        "count": len(rots), "fraction": round(len(rots) / R, 3)})
    return {"threshold": threshold, "rotations": R, "minSize": min_size, "maxSize": max_size,
            "groups": maximal,
            "note": "Descriptive only: recurring co-seating may reflect sincere preferences, forced structures, "
                    "small eligible pools, or chance. It is not evidence of intent."}


def recurring_group_report(rotations, ids=None, key="tables", **kw):
    """Convenience wrapper over trace rotation records (proposed or random charts)."""
    result = recurring_groups([r[key] for r in rotations], **kw)
    if ids is not None:
        for g in result["groups"]:
            g["members"] = [ids[m] if isinstance(m, int) else m for m in g["members"]]
    return result
