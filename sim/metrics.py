"""Individual outcome metrics for evaluating the mixing trade-off.

All statistics are computed from the released charts.  Coverage statistics use
obligated, present students as the denominator; participation and admission
are reported separately so that exclusions cannot improve coverage.  "Distinct
peers" counts students seated together; an unlisted tablemate is not assumed
to be a stranger, and exactly-one coverage is an optimisation statistic, not a
measure of wellbeing.
"""
from __future__ import annotations


def _quantile(sorted_values, f):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * f
    lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo))


def distribution(values):
    v = sorted(values)
    if not v:
        return {"n": 0}
    return {"n": len(v), "min": v[0], "p5": round(_quantile(v, .05), 2), "p10": round(_quantile(v, .10), 2),
            "q1": round(_quantile(v, .25), 2), "median": round(_quantile(v, .5), 2),
            "q3": round(_quantile(v, .75), 2), "max": v[-1], "mean": round(sum(v) / len(v), 2)}


def individual_outcomes(rotations, ids, lists, grade, *, key="tables", present_key="present",
                        states=None):
    """Per-student outcomes over a year of charts.

    ``rotations`` are trace rotation records with ``tables`` (or ``key``) and
    optionally ``absent`` / ``waivedObligations``; ``lists`` map id -> set of
    listed ids (the effective obligation); ``grade`` maps id -> grade.
    """
    ids = list(ids)
    listed = {i: set(lists.get(i, ())) for i in ids}
    distinct = {i: set() for i in ids}
    rot_present = {i: 0 for i in ids}
    rot_obligated = {i: 0 for i in ids}
    ge1 = {i: 0 for i in ids}
    ex1 = {i: 0 for i in ids}
    ge2 = {i: 0 for i in ids}
    extras = {i: 0 for i in ids}
    companion_counts = {i: {} for i in ids}      # listed peer -> rotations together
    for r in rotations:
        state = r.get("state", "mixed")
        absent = set(r.get("absent", []))
        waived = set((r.get("waivedObligations") or {}).keys())
        for tbl in r[key]:
            members = set(tbl)
            for i in tbl:
                if i in absent:
                    continue
                rot_present[i] += 1
                peers = members - {i}
                distinct[i].update(peers)
                if not listed[i] or i in waived:
                    continue
                eligible = {j for j in listed[i] if state == "mixed" or grade[j] == grade[i]}
                here = peers & eligible
                rot_obligated[i] += 1
                if here:
                    ge1[i] += 1
                if len(here) == 1:
                    ex1[i] += 1
                if len(here) >= 2:
                    ge2[i] += 1
                extras[i] += max(0, len(here) - 1)
                for j in here:
                    companion_counts[i][j] = companion_counts[i].get(j, 0) + 1
    per_student = {}
    for i in ids:
        cc = companion_counts[i]
        top = max(cc.values()) if cc else 0
        per_student[i] = {
            "distinctPeers": len(distinct[i]), "rotationsPresent": rot_present[i],
            "rotationsObligated": rot_obligated[i], "atLeastOne": ge1[i], "exactlyOne": ex1[i],
            "twoOrMore": ge2[i], "extraCompanions": extras[i],
            "distinctListedCompanions": len(cc), "maxRepeatWithSameListedPeer": top,
            "listedCompanionConcentration": round(top / rot_obligated[i], 3) if rot_obligated[i] else None,
        }
    obligated = [i for i in ids if rot_obligated[i] > 0]
    total_obl = sum(rot_obligated[i] for i in obligated)
    return {
        "perStudent": per_student,
        "coverageAmongObligated": {
            "students": len(obligated), "obligatedStudentRotations": total_obl,
            "atLeastOnePct": round(100 * sum(ge1.values()) / total_obl, 2) if total_obl else None,
            "exactlyOnePct": round(100 * sum(ex1.values()) / total_obl, 2) if total_obl else None,
            "twoOrMorePct": round(100 * sum(ge2.values()) / total_obl, 2) if total_obl else None,
            "studentsAlwaysAtLeastOne": sum(1 for i in obligated if ge1[i] == rot_obligated[i]),
        },
        "extraCompanions": {"total": sum(extras.values()),
                            "perObligatedRotation": round(sum(extras.values()) / total_obl, 4) if total_obl else None,
                            "distribution": distribution([extras[i] for i in obligated])},
        "distinctPeers": distribution([len(distinct[i]) for i in ids]),
        "distinctPeersObligated": distribution([len(distinct[i]) for i in obligated]),
        "repeatedCompanionship": {
            "maxRepeatWithSameListedPeer": distribution([per_student[i]["maxRepeatWithSameListedPeer"] for i in obligated]),
            "distinctListedCompanions": distribution([per_student[i]["distinctListedCompanions"] for i in obligated]),
            "concentration": distribution([per_student[i]["listedCompanionConcentration"] for i in obligated
                                           if per_student[i]["listedCompanionConcentration"] is not None]),
        },
        "note": "Distinct peers count students seated together; unlisted tablemates are not assumed unfamiliar. "
                "Exactly-one coverage is an optimisation statistic, not a wellbeing measure.",
    }


def participation_summary(rotations, ids, submission_summary):
    """Participation and admission, separate from guarantee satisfaction."""
    R = len(rotations)
    present = [len(ids) - len(r.get("absent", [])) for r in rotations]
    waived = [len(r.get("waivedObligations") or {}) for r in rotations]
    return {"rotations": R, "roster": len(ids),
            "presentPerRotation": present, "absentPerRotation": [len(r.get("absent", [])) for r in rotations],
            "meanPresent": round(sum(present) / R, 2) if R else None,
            "waivedObligationsPerRotation": waived,
            "submissionStates": submission_summary["counts"],
            "pendingReview": submission_summary["pendingReview"],
            "approvedExceptions": submission_summary["approvedExceptions"],
            "voluntaryNonsubmission": submission_summary["voluntaryNonsubmission"],
            "obligatedStudents": submission_summary["obligated"]}
