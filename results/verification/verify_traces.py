"""Independent saved-trace check; uses only the Python standard library.

Usage: python results/verification/verify_traces.py MANIFEST --out CHECKS.json
Recomputes charts, stage costs, output statistics, outcome distributions and
trace file hashes without calling any sim module or trusting cached summaries.
"""
from collections import Counter
from itertools import combinations
import argparse
import hashlib
import json
from pathlib import Path


def check_trace(trace):
    cfg = trace['config']
    ids = [s['id'] for s in trace['students']]
    grades = {s['id']: s['grade'] for s in trace['students']}
    lists = dict(zip(ids, map(set, trace['listed'])))
    caps, table_grade = cfg['tableCapacities'], cfg['sameGradeTableGrade']
    n = len(ids)
    errors = []
    def check(actual, expected, label):
        if actual != expected:
            errors.append({'field': label, 'actual': actual, 'expected': expected})
    check(len(set(ids)), n, 'unique population IDs')
    check(sum(caps), n, 'seat total')
    check(len(trace['rotations']), cfg['rotations'], 'horizon')
    provenance = cfg.get('provenance')
    if provenance:
        def fingerprint(value):
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
            return hashlib.sha256(encoded).hexdigest()
        check(provenance['effectiveSourceHash'], fingerprint(provenance['sourceFiles']), 'source fingerprint')
        inputs = provenance['effectiveInputs']
        check(provenance['inputHash'], fingerprint(inputs), 'effective input fingerprint')
        check([[ids[j] for j in row] for row in inputs['submittedLists']], trace['listed'], 'effective submitted lists')
        check(inputs['network']['grade'], [grades[i] for i in ids], 'effective grade vector')
        check(provenance['populationSeed'], inputs['network']['seed'], 'population seed provenance')
        check(provenance['solverSeed'], inputs['runConfig']['seed'], 'solver seed provenance')
    histories = {'tables': Counter(), 'tablesRandom': Counter()}
    sym_listed = {tuple(sorted((a, b))) for a in ids for b in lists[a]}
    per_rotation = []
    coalition = set(cfg.get('coalition', []))
    for idx, rot in enumerate(trace['rotations']):
        label = f'rotation {idx + 1}'
        check(rot['idx'], idx + 1, label + ' index')
        first = cfg.get('firstState', 'mixed')
        expected_state = first if idx % 2 == 0 else {'mixed': 'same', 'same': 'mixed'}[first]
        check(rot['state'], expected_state, label + ' schedule')
        eligible = {i: {j for j in lists[i] if rot['state'] == 'mixed' or grades[j] == grades[i]} for i in ids}
        stats = {}
        for key in ('tables', 'tablesRandom'):
            tables = rot[key]
            check(len(tables), len(caps), label + ' ' + key + ' table count')
            flat = [i for t in tables for i in t]
            check(sorted(flat), sorted(ids), label + ' ' + key + ' unique placement')
            counts = {}
            mates = {}
            for t, members in enumerate(tables):
                check(len(members), caps[t], label + f' {key} table {t} capacity')
                if rot['state'] == 'same':
                    check(all(grades[i] == table_grade[t] for i in members), True,
                          label + f' {key} table {t} grade')
                for i in members:
                    mates[i] = set(members) - {i}
                    if lists[i]:
                        counts[i] = len(mates[i] & eligible[i])
            if key == 'tables':
                check([i for i, count in counts.items() if count == 0], [], label + ' guarantee')
            anchors = rot['anchors' if key == 'tables' else 'anchorsRandom']
            expected_anchor_ids = sorted(i for i, count in counts.items() if count > 0)
            check(sorted(anchors), expected_anchor_ids, label + ' ' + key + ' anchor coverage')
            for i, j in anchors.items():
                check(j in mates[i] & eligible[i], True, label + f' {key} anchor {i}')
            pairs = {tuple(sorted(pair)) for t in tables for pair in combinations(t, 2)}
            history = histories[key]
            repeat_count = sum(history[pair] > 0 for pair in pairs)
            suffix = '' if key == 'tables' else 'Random'
            def pct(predicate):
                return round(100 * sum(predicate(c) for c in counts.values()) / len(counts), 2) if counts else 0.0
            values = {f'pctGe1{suffix}': pct(lambda c: c >= 1),
                      f'pctExactly1{suffix}': pct(lambda c: c == 1),
                      f'pctGe2{suffix}': pct(lambda c: c >= 2),
                      f'repeatPairs{suffix}': repeat_count}
            if key == 'tables':
                stage_records = rot.get('pipeline', [])
                for stage in stage_records:
                    stage_label = label + ' pipeline ' + stage['name']
                    stage_tables = stage['tables']
                    check(sorted(i for t in stage_tables for i in t), sorted(ids), stage_label + ' unique placement')
                    check([len(t) for t in stage_tables], caps, stage_label + ' capacities')
                    if rot['state'] == 'same':
                        check(all(grades[i] == table_grade[t] for t, members in enumerate(stage_tables) for i in members),
                              True, stage_label + ' grades')
                    stage_counts = [len((set(t) - {i}) & eligible[i]) for t in stage_tables for i in t if lists[i]]
                    viol = sum(c == 0 for c in stage_counts)
                    extras = sum(max(0, c - 1) for c in stage_counts)
                    stage_pairs = {tuple(sorted(p)) for t in stage_tables for p in combinations(t, 2)}
                    weight = cfg['weights']['anneal']
                    repeat_energy = sum(history[p] * (weight['repeatListedPerMeeting'] if p in sym_listed else
                                                     weight['repeatIncidentalPerMeeting']) for p in stage_pairs)
                    repeat_scaled = round(10 * repeat_energy)
                    cost = {'violations': viol, 'twoPlus': sum(c >= 2 for c in stage_counts),
                            'extraPeers': extras, 'repeat': repeat_scaled,
                            'total': round(10 * (weight['satisfied'] * viol + weight['extraPeer'] * extras)) + repeat_scaled}
                    for k, v in cost.items():
                        check(stage['cost'][k], v, stage_label + ' cost.' + k)
                if stage_records:
                    check(stage_records[-1]['tables'], tables, label + ' final-stage chart')
                    check(stage_records[-1]['cost'], rot['stats']['cost'], label + ' final-stage cost')
            history.update(pairs)
            values[f'meanDistinctMet{suffix}'] = round(2 * len(history) / n, 2)
            stats.update(values)
            for k, v in values.items():
                check(rot['stats'][k], v, label + ' ' + k)
            if coalition:
                sizes = sorted((len(set(t) & coalition) for t in tables if set(t) & coalition), reverse=True)
                record = rot['coalition' if key == 'tables' else 'coalitionRandom']
                values = {'maxCluster': max(sizes), 'avgCluster': round(sum(s*s for s in sizes) / len(coalition), 2),
                          'intact': len(sizes) == 1, 'pattern': '+'.join(map(str, sizes))}
                for k, v in values.items():
                    check(record[k], v, label + ' ' + key + ' coalition.' + k)
        per_rotation.append(stats)
    distinct = {i: sum(i in p for p in histories['tables']) for i in ids}
    ordered_values = sorted(distinct.values())
    quantiles = {'min': min(ordered_values), 'max': max(ordered_values),
                 'mean': round(sum(ordered_values) / n, 2),
                 **{key: float(ordered_values[min(n-1, round(f*(n-1)))])
                    for key, f in [('q1', .25), ('median', .5), ('q3', .75)]}}
    check(trace['fairness']['distinctMet'], quantiles, 'fairness distinct quantiles')
    indegree = Counter(j for l in lists.values() for j in l)
    order = sorted(ids, key=lambda i: (indegree[i], i))
    q = n // 4
    for field, subset in [('lowestInDegreeQuartile', order[:q]), ('highestInDegreeQuartile', order[-q:])]:
        result = {'n': q, 'meanInDegree': round(sum(indegree[i] for i in subset) / q, 2),
                  'meanDistinctMet': round(sum(distinct[i] for i in subset) / q, 2)}
        check(trace['fairness'][field], result, 'fairness ' + field)
    result = {'pctGe1Min': min(r['pctGe1'] for r in per_rotation),
              'pctExactly1Mean': round(sum(r['pctExactly1'] for r in per_rotation) / len(per_rotation), 2),
              'pctExactly1Min': min(r['pctExactly1'] for r in per_rotation),
              'pctGe1RandomMean': round(sum(r['pctGe1Random'] for r in per_rotation) / len(per_rotation), 2),
              'meanDistinctMetFinal': per_rotation[-1]['meanDistinctMet'],
              'meanDistinctMetFinalRandom': per_rotation[-1]['meanDistinctMetRandom'],
              'repeatsWorseThanRandomRotations': [i+1 for i, r in enumerate(per_rotation)
                                                if r['repeatPairs'] > r['repeatPairsRandom']]}
    if coalition:
        rots = trace['rotations']
        result.update(coalitionIntactRotations=sum(r['coalition']['intact'] for r in rots),
                      coalitionAvgCluster=round(sum(r['coalition']['avgCluster'] for r in rots) / len(rots), 2),
                      coalitionPatterns=dict(Counter(r['coalition']['pattern'] for r in rots)))
    for k, v in result.items():
        check(trace['summary'][k], v, 'summary ' + k)
    return {'errors': errors, 'rotationsChecked': len(per_rotation),
            'proposedAndRandomChartsChecked': len(per_rotation) * 2,
            'pipelineChartsChecked': sum(len(r.get('pipeline', [])) for r in trace['rotations']),
            'independentSummary': result}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text())
    reports = []
    for attempt in manifest['attempts']:
        if not attempt.get('traceEvidence') or attempt['status'] == 'evidence_unavailable':
            continue
        evidence = attempt['traceEvidence']
        path = args.manifest.parent / evidence['path']
        raw = path.read_bytes()
        report = check_trace(json.loads(raw))
        if hashlib.sha256(raw).hexdigest() != evidence['sha256']:
            report['errors'].append({'field': 'trace hash', 'actual': hashlib.sha256(raw).hexdigest(), 'expected': evidence['sha256']})
        report.update(attemptId=attempt['id'], tracePath=str(path), status=attempt['status'],
                      populationSeed=attempt['configuration']['populationSeed'], scenario=attempt['configuration']['scenario'])
        reports.append(report)
    output = {'manifest': str(args.manifest), 'manifestSha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
              'attemptDenominator': len(manifest['attempts']),
              'attemptStatuses': dict(Counter(a['status'] for a in manifest['attempts'])),
              'tracesChecked': len(reports), 'totalDiscrepancies': sum(len(r['errors']) for r in reports),
              'reports': reports}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({k: v for k, v in output.items() if k != 'reports'}, indent=2))
    if output['totalDiscrepancies']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
