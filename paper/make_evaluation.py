#!/usr/bin/env python
"""Summarise the method-comparison ledger into tables and JSON.

    python paper/make_evaluation.py --manifest results/revised_evaluation.json

For every (condition, method) group the report gives the attempt outcomes
(scheduled, review required, proven infeasible, unknown, other), runtime,
objective components, coverage among obligated students, individual outcome
distributions (distinct peers, repeated companionship), fallback frequency and
the matched random baseline computed inside the same runs. Trace identities and
chart-level quantities are checked before aggregating the retained outcome
fields. The publication audit separately recomputes individual outcomes and
exposure from raw charts; this table builder is not that independent checker.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper.assemble_evidence import verify_attempt  # noqa: E402
from results.verification.verify_traces import check_trace  # noqa: E402

STATUS_LABELS = {"success": "scheduled", "review_required": "review", "infeasible_input": "infeasible",
                 "unknown": "unknown", "error": "error", "interrupted": "interrupted",
                 "interrupted_unfinished": "interrupted", "source_changed": "excluded",
                 "evidence_unavailable": "excluded", "running": "unfinished"}


def esc(value):
    return str(value).replace('&', r'\&').replace('%', r'\%').replace('_', r'\_').replace('#', r'\#')


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def fmt(value, digits=2):
    return "--" if value is None else f"{value:.{digits}f}"


def table(name, caption, header, rows, spec):
    return '\n'.join((r'\begin{table}[tb]\centering\scriptsize\setlength{\tabcolsep}{4pt}',
                      r'\caption{' + caption + r'}\label{tab:' + name + '}',
                      r'\begin{tabular}{@{}' + spec + r'@{}}\toprule',
                      ' & '.join(header) + r' \\ \midrule',
                      *(' & '.join(map(str, row)) + r' \\' for row in rows),
                      r'\bottomrule\end{tabular}\end{table}', ''))


def summarise(manifest_path, retained_source=False, verify=True):
    manifest = json.loads(manifest_path.read_text())
    groups = defaultdict(lambda: {"attempts": [], "traces": []})
    for attempt in manifest["attempts"]:
        cfg = attempt["configuration"]
        key = (cfg.get("condition", cfg["scenario"]), cfg["run"]["method"])
        groups[key]["attempts"].append(attempt)
        if attempt["status"] == "success":
            if verify:
                verify_attempt(attempt, manifest_path, retained_source=retained_source)
            trace = json.loads((manifest_path.parent / attempt["traceEvidence"]["path"]).read_text())
            if verify:
                report = check_trace(trace)
                if report["errors"]:
                    raise ValueError(f"independent recomputation found discrepancies in {attempt['id']}: {report['errors'][:3]}")
            groups[key]["traces"].append(trace)
    rows = {}
    for (condition, method), group in sorted(groups.items()):
        statuses = defaultdict(int)
        for a in group["attempts"]:
            statuses[STATUS_LABELS.get(a["status"], a["status"])] += 1
        traces = group["traces"]
        rec = {"condition": condition, "method": method, "attempts": len(group["attempts"]),
               "statuses": dict(statuses), "runs": len(traces)}
        if traces:
            def agg(fn):
                return mean([fn(t) for t in traces])
            rots = lambda t: t["rotations"]  # noqa: E731
            rec.update({
                "rotations": traces[0]["config"]["rotations"],
                "yearSolveSeconds": agg(lambda t: t["config"]["yearSolveSeconds"]),
                "meanSolveSecondsPerRotation": agg(lambda t: mean([r["stats"]["solveTime"] for r in rots(t)])),
                "atLeastOnePct": agg(lambda t: t["outcomes"]["proposed"]["coverageAmongObligated"]["atLeastOnePct"]),
                "exactlyOnePct": agg(lambda t: t["outcomes"]["proposed"]["coverageAmongObligated"]["exactlyOnePct"]),
                "exactlyOnePctRandom": agg(lambda t: t["outcomes"]["random"]["coverageAmongObligated"]["exactlyOnePct"]),
                "atLeastOnePctRandom": agg(lambda t: t["outcomes"]["random"]["coverageAmongObligated"]["atLeastOnePct"]),
                "extrasPerObligatedRotation": agg(lambda t: t["outcomes"]["proposed"]["extraCompanions"]["perObligatedRotation"]),
                "objectiveTotal": agg(lambda t: t["summary"]["objectiveTotal"]),
                "repeatCostTotal": agg(lambda t: sum(r["stats"]["cost"]["repeat"] for r in rots(t)) /
                                       t["config"]["objective"]["integerScale"]),
                "distinctPeersMean": agg(lambda t: t["outcomes"]["proposed"]["distinctPeers"]["mean"]),
                "distinctPeersMin": agg(lambda t: t["outcomes"]["proposed"]["distinctPeers"]["min"]),
                "distinctPeersP10": agg(lambda t: t["outcomes"]["proposed"]["distinctPeers"]["p10"]),
                "distinctPeersMeanRandom": agg(lambda t: t["outcomes"]["random"]["distinctPeers"]["mean"]),
                "distinctPeersMinRandom": agg(lambda t: t["outcomes"]["random"]["distinctPeers"]["min"]),
                "maxRepeatSameListedPeerMedian": agg(lambda t: t["outcomes"]["proposed"]["repeatedCompanionship"]["maxRepeatWithSameListedPeer"]["median"]),
                "maxRepeatSameListedPeerMax": agg(lambda t: t["outcomes"]["proposed"]["repeatedCompanionship"]["maxRepeatWithSameListedPeer"]["max"]),
                "fallbackRotations": agg(lambda t: len(t["summary"].get("fallbackRotations", []))),
                "incumbentRotations": agg(lambda t: len(t["summary"].get("incumbentRotations", []))),
                "optimalityProvenRotations": agg(lambda t: len(t["summary"].get("optimalityProvenRotations", []))),
                "waivedObligations": agg(lambda t: sum(t["outcomes"]["participation"]["waivedObligationsPerRotation"])),
                "meanPresent": agg(lambda t: t["summary"]["meanPresent"]),
                "pendingReview": agg(lambda t: len(t["config"]["submissions"]["pendingReview"])),
                "approvedExceptions": agg(lambda t: len(t["config"]["submissions"]["approvedExceptions"])),
                "voluntaryNonsubmission": agg(lambda t: len(t["config"]["submissions"]["voluntaryNonsubmission"])),
                "obligatedStudents": agg(lambda t: t["config"]["submissions"]["obligated"]),
                "leakageForced": agg(lambda t: t["leakage"]["forcedEdges"]),
                "exposureTop1": agg(lambda t: t["leakage"]["coseatingExposure"]["proposed"]["top1ListedRate"]),
                "exposureTop1Random": agg(lambda t: t["leakage"]["coseatingExposure"]["random"]["top1ListedRate"]),
            })
        rows[f"{condition}/{method}"] = rec
    return {"manifest": str(manifest_path.relative_to(ROOT)) if manifest_path.is_relative_to(ROOT) else str(manifest_path),
            "attemptCount": len(manifest["attempts"]),
            "partial": manifest.get("assembly", {}).get("partial", False),
            "unfinishedAttempts": sum(a["status"] == "running" for a in manifest["attempts"]),
            "sourceHashes": sorted({a["source"]["effectiveSourceHash"] for a in manifest["attempts"]}),
            "groups": rows}


def render(summary, out_dirs):
    rows = list(summary["groups"].values())
    scope = ("The planned grid is incomplete; methods have unequal population, solver-seed, and retry coverage. "
             if summary.get("partial") else "")
    outcome_rows = []
    for r in rows:
        st = r["statuses"]
        outcome_rows.append([esc(r["condition"]), esc(r["method"]), r["attempts"], st.get("scheduled", 0),
                             st.get("review", 0), st.get("infeasible", 0), st.get("unknown", 0),
                             r["attempts"] - st.get("scheduled", 0) - st.get("review", 0) - st.get("infeasible", 0) - st.get("unknown", 0),
                             fmt(r.get("yearSolveSeconds"), 0), fmt(r.get("fallbackRotations"), 1)])
    tables = {}
    tables["evaluation_outcomes"] = table(
        "evalOutcomes", scope + "Method comparison: retained attempt outcomes per condition. Scheduled means every rotation released "
        "an independently validated chart; review, infeasible and unknown are the explicit non-scheduled outcomes. "
        "Runtime is the mean wall-clock year time on a shared machine. Fallback counts rotations that released the "
        "unchanged validated fallback chart. Other includes interruptions and "
        f"{summary.get('unfinishedAttempts', 0)} attempts still marked running in the saved ledgers; these have no terminal outcome.",
        ["Condition", "Method", "Att.", "Sched.", "Review", "Infeas.", "Unknown", "Other", "Year s", "Fallback rot."],
        outcome_rows, "llrrrrrrrr")
    quality_rows = []
    for r in rows:
        if not r.get("runs"):
            continue
        quality_rows.append([esc(r["condition"]), esc(r["method"]), r["runs"],
                             fmt(r["atLeastOnePct"], 1), fmt(r["exactlyOnePct"], 1),
                             fmt(r["extrasPerObligatedRotation"], 3), fmt(r["objectiveTotal"], 1),
                             fmt(r["distinctPeersMean"], 1), fmt(r["distinctPeersMeanRandom"], 1),
                             fmt(r["distinctPeersP10"], 1), fmt(r["distinctPeersMin"], 0),
                             fmt(r["maxRepeatSameListedPeerMedian"], 1), fmt(r["exposureTop1"], 2)])
    tables["evaluation_quality"] = table(
        "evalQuality", scope + "Unpaired summaries of scheduled runs: coverage among obligated students (\\%), extra listed "
        "companions per obligated student-rotation, total unscaled objective over the year, distinct peers per student "
        "(mean; matched random mean; 10th percentile; minimum), median over students of the maximum number of "
        "rotations spent with the same listed peer, and the fraction of obligated students whose most frequent "
        "tablemate is a listed peer (statistical exposure). Means over runs.",
        ["Condition", "Method", "Runs", "$\\ge1$", "$=1$", "Extras", "Obj.", "Peers", "Rand.", "P10", "Min", "Rep.", "Exp."],
        quality_rows, "llrrrrrrrrrrr")
    for out in out_dirs:
        (out / "generated").mkdir(parents=True, exist_ok=True)
        for name, content in tables.items():
            (out / "generated" / f"{name}.tex").write_text(content)
    return tables


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=ROOT / "results" / "revised_evaluation.json")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "evaluation_summary.json")
    ap.add_argument("--retained-source", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args(argv)
    summary = summarise(args.manifest.resolve(), retained_source=args.retained_source, verify=not args.no_verify)
    args.out.write_text(json.dumps(summary, indent=1) + "\n")
    render(summary, (ROOT / "article", ROOT / "paper"))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("attempts", "statuses", "runs", "yearSolveSeconds", "fallbackRotations")}
                      for k, v in summary["groups"].items()}, indent=1))


if __name__ == "__main__":
    main()
