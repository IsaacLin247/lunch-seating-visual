#!/usr/bin/env python
"""Student-facing chart export: the assignment and nothing private.

    python sim/student_export.py docs/data/honest.json --rotation 3 --out chart.json
    python sim/student_export.py trace.json --history --out year.json   # explicit opt-in

A full trace contains submitted lists, anchors, review information, screening
diagnostics, solver internals, the random comparison and inference results.
None of that belongs in anything distributed to students.  This export keeps
only the seating of the requested rotation (student IDs and grades per table).
Distributing one current assignment at a time, and not an archive, limits what
an observer can accumulate; it does not make the assignment confidential (see
docs/policy/data_handling_policy.md), and a public web page is not access
control.
"""
from __future__ import annotations

import argparse
import json
import sys

PRIVATE_TRACE_KEYS = frozenset({
    "listed", "listedInitial", "hero", "fairness", "leakage", "outcomes", "summary", "submissions",
})
PRIVATE_CONFIG_KEYS = frozenset({
    "screen", "diagnosticScreen", "fullModelScreen", "submission", "submissions", "feasibility", "provenance",
    "weights", "objective", "network", "generator", "baseline", "coalition", "coalitionMode", "versions",
    "solver", "attendance", "staff", "fallbacks", "reviewDecisions", "recurringGroups",
})
PRIVATE_ROTATION_KEYS = frozenset({
    "anchors", "anchorsRandom", "tablesRandom", "stats", "pipeline", "coalition", "coalitionRandom",
    "waivedObligations", "conflicts", "fallback", "cpsat", "attendance", "release",
})
STUDENT_NOTICE = ("This chart shows table assignments only. Submitted lists are confidential and are not "
                  "included. Seating patterns over time can still suggest who listed whom; the school's "
                  "data-handling policy explains this limit.")


def student_facing_export(trace, rotation=None, *, include_history=False, include_grade=True):
    """Return a chart-only export for one rotation (default: the last one)."""
    students = {s["id"]: s for s in trace["students"]}
    rotations = trace["rotations"]
    if not include_history:
        idx = (len(rotations) - 1) if rotation is None else rotation - 1
        if not 0 <= idx < len(rotations):
            raise ValueError("rotation out of range")
        selected = [rotations[idx]]
    else:
        selected = list(rotations)

    def table_rows(r):
        return [[{"id": i, "grade": students[i]["grade"]} if include_grade else {"id": i} for i in tbl]
                for tbl in r["tables"]]
    out = {
        "kind": "student-facing seating chart",
        "notice": STUDENT_NOTICE,
        "includesHistory": include_history,
        "rotations": [{"idx": r["idx"], "state": r["state"], "tables": table_rows(r),
                       "absent": list(r.get("absent", []))} for r in selected],
    }
    if include_history:
        out["historyWarning"] = ("Every additional published chart narrows the set of lists consistent with "
                                 "the observed tables; distribute history only when the policy permits it.")
    assert_no_private_data(out)
    return out


def assert_no_private_data(export):
    """Raise if the export carries any private key at any depth."""
    banned = PRIVATE_TRACE_KEYS | PRIVATE_CONFIG_KEYS | PRIVATE_ROTATION_KEYS

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in banned:
                    raise ValueError(f"private field {'/'.join(path + [k])} present in a student-facing export")
                walk(v, path + [k])
        elif isinstance(node, list):
            for k, v in enumerate(node):
                walk(v, path + [str(k)])
    walk(export, [])
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("--rotation", type=int, help="1-based rotation to distribute (default: the last)")
    ap.add_argument("--history", action="store_true", help="include every rotation (explicit opt-in)")
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--out", help="output path (default: stdout)")
    args = ap.parse_args(argv)
    with open(args.trace) as f:
        trace = json.load(f)
    export = student_facing_export(trace, args.rotation, include_history=args.history, include_grade=not args.no_grade)
    text = json.dumps(export, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
