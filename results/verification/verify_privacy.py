"""Independent CP-SAT exclusion proofs for the chart-only leakage headline.

The production probe uses bitmask dynamic programming. This checker independently
uses binary set cover, then tests each member of a found cover for exclusion
under the public cap. A name forced in every cover must belong to that cover, so
these exclusion tests suffice. Private lists are used only to identify known
submitters and score recovered positives after inference.
"""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
import platform
import ortools
from pathlib import Path
from ortools.sat.python import cp_model


def cover(sets, cap, excluded=None):
    names = sorted(set().union(*sets) - ({excluded} if excluded else set()))
    model = cp_model.CpModel()
    x = {name: model.new_bool_var(name) for name in names}
    for peers in sets:
        model.add(sum(x[j] for j in sorted(peers) if j != excluded) >= 1)
    model.add(sum(x.values()) <= cap)
    if excluded is None:
        model.minimize(sum(x.values()))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_deterministic_time = 2.0
    status = solver.solve(model)
    name = solver.status_name(status)
    witness = [j for j in names if solver.value(x[j])] if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    return name, witness


def check(trace):
    ids = [s['id'] for s in trace['students']]
    truth = dict(zip(ids, map(set, trace['listed'])))
    cap = trace['leakage']['kMax']
    peer_sets = {i: [] for i in ids}
    for rotation in trace['rotations']:
        for table in rotation['tables']:
            for i in table:
                peer_sets[i].append(set(table) - {i})
    forced = {}
    proofs, unresolved = [], []
    for i in ids:
        if not truth[i]:
            continue
        status, initial = cover(peer_sets[i], cap)
        if initial is None:
            unresolved.append({'student': i, 'initialStatus': status})
            continue
        for j in initial:
            status, witness = cover(peer_sets[i], cap, excluded=j)
            if status == 'INFEASIBLE':
                forced.setdefault(i, []).append(j)
                proofs.append({'student': i, 'forcedName': j, 'excludedStatus': status})
            elif witness is None:
                unresolved.append({'student': i, 'excludedName': j, 'status': status})
    n_edges = sum(map(len, truth.values()))
    edges = sum(map(len, forced.values()))
    metrics = {'forcedEdges': edges,
               'forcedEdgesCorrect': sum(j in truth[i] for i, names in forced.items() for j in names),
               'studentsWithForcedEdge': len(forced),
               'fullyDeterminedStudents': sorted(i for i, names in forced.items() if len(names) == min(cap, len(ids)-1)),
               'completeTruePositiveRecoveryStudents': sorted(i for i, names in forced.items() if truth[i] <= set(names)),
               'submittedEdges': n_edges, 'fractionOfEdgesForced': round(edges/n_edges, 4) if n_edges else 0.0}
    errors = [{'field': k, 'actual': trace['leakage'].get(k), 'expected': v} for k, v in metrics.items()
              if trace['leakage'].get(k) != v]
    return {'method': 'independent binary set-cover/exclusion CP-SAT model; 2 deterministic units per check, one worker',
            'provenForcedEntries': len(proofs), 'unresolved': unresolved, 'errors': errors,
            'independentMetrics': metrics, 'exclusionProofs': proofs}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--no-reuse', action='store_true', help='recheck even identical previously verified traces')
    args = ap.parse_args()
    manifest_raw = args.manifest.read_bytes()
    manifest = json.loads(manifest_raw)
    checker_identity = {'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        'python': platform.python_version(), 'ortools': ortools.__version__}
    cached = {}
    if args.out.exists() and not args.no_reuse:
        previous = json.loads(args.out.read_text())
        if previous.get('checkerIdentity') == checker_identity:
            cached = {r['attemptId']: r for r in previous.get('reports', [])
                      if not r['errors'] and not r['unresolved']}
    reports, reused = [], 0
    for attempt in manifest['attempts']:
        if not attempt.get('traceEvidence') or attempt['status'] == 'evidence_unavailable':
            continue
        path = args.manifest.parent / attempt['traceEvidence']['path']
        trace_raw = path.read_bytes()
        trace_sha256 = hashlib.sha256(trace_raw).hexdigest()
        previous = cached.get(attempt['id'])
        if previous and previous['traceSha256'] == trace_sha256:
            reports.append(previous)
            reused += 1
            print(previous['populationSeed'], previous['scenario'], 'reused identical verified trace', flush=True)
            continue
        report = check(json.loads(trace_raw))
        report.update(attemptId=attempt['id'], tracePath=str(path),
                      checkedAt=datetime.now(timezone.utc).isoformat(), traceSha256=trace_sha256,
                      populationSeed=attempt['configuration']['populationSeed'], scenario=attempt['configuration']['scenario'])
        reports.append(report)
        print(report['populationSeed'], report['scenario'], report['provenForcedEntries'],
              'forced entries;', len(report['errors']), 'discrepancies;', len(report['unresolved']), 'unresolved', flush=True)
    output = {'manifest': str(args.manifest), 'manifestSha256': hashlib.sha256(manifest_raw).hexdigest(),
              'generatedAt': datetime.now(timezone.utc).isoformat(),
              'checkerIdentity': checker_identity, 'reusedTraceChecks': reused,
              'tracesChecked': len(reports), 'totalProvenForcedEntries': sum(r['provenForcedEntries'] for r in reports),
              'totalDiscrepancies': sum(len(r['errors']) for r in reports),
              'totalUnresolved': sum(len(r['unresolved']) for r in reports), 'reports': reports}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + '\n')
    if output['totalDiscrepancies'] or output['totalUnresolved']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
