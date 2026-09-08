#!/usr/bin/env python
"""Merge auditable experiment manifests and publish their six seed-7 references.

Default inputs are results/verified_core_a.json, verified_core_b.json and
verified_sensitivity.json. Existing historical results/experiments.json is never
read. Every attempt, batch and successful category row is retained. Trace files
remain in place; their references are rewritten relative to the output manifest.
Unfinished/missing inputs require --partial. After later source repairs, use
--retained-source to verify every source byte in results/source_snapshots/HASH;
this does not waive source checks. Site export waits until every
reference scenario at the default 16-rotation budget has a verified full trace.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ('seeds', 'budgets', 'communities', 'horizons')
REFERENCES = ('honest', 'coalition_none', 'coalition_min4', 'coalition_stratified',
              'coalition_shared_anchor', 'coalition_screened')
DEFAULT_INPUTS = [ROOT / 'results' / name for name in
                  ('verified_core_a.json', 'verified_core_b.json', 'verified_sensitivity.json')]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_bytes(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_json(path, value):
    atomic_bytes(path, (json.dumps(value, indent=1, allow_nan=False) + '\n').encode())


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def verify_attempt(attempt, input_path, *, retained_source=False):
    """Check identity chains independently of sim.provenance's implementation."""
    source = attempt['source']
    identity = source['effectiveSourceHash']
    ensure(identity == fingerprint(source['sourceFiles']), f"bad source fingerprint in {attempt['id']}")
    ensure(attempt['fingerprint'] == fingerprint({
        'configuration': {'category': attempt['category'], **attempt['configuration']},
        'effectiveSourceHash': identity, 'versions': source['versions']}),
        f"bad resume fingerprint in {attempt['id']}")
    source_root = ROOT / 'results' / 'source_snapshots' / identity if retained_source else ROOT
    for filename, expected in source['sourceFiles'].items():
        path = source_root / filename
        ensure(path.is_file() and digest(path) == expected,
               f"effective source differs from retained identity: {path}")
    evidence = attempt.get('traceEvidence')
    if attempt['status'] == 'evidence_unavailable':
        ensure(attempt.get('originalTerminalStatus') == 'success',
               f"unavailable evidence lacks original terminal status: {attempt['id']}")
        # Retain the failed evidence record in the denominator, but it is no
        # longer represented as a checked trace or a verified summary row.
        return None
    if attempt['status'] == 'success':
        ensure(evidence is not None and evidence.get('validation') == 'passed',
               f"success without validated full trace: {attempt['id']}")
        ensure(attempt.get('sourceUnchangedDuringRun') is True,
               f"success lacks stable-source evidence: {attempt['id']}")
    if not evidence:
        return None
    path = (input_path.parent / evidence['path']).resolve()
    ensure(path.is_file() and digest(path) == evidence['sha256'],
           f"missing or changed trace evidence: {path}")
    trace = json.loads(path.read_text())
    prov = trace['config']['provenance']
    ensure(prov['effectiveSourceHash'] == identity, f"trace/attempt source mismatch: {path}")
    ensure(prov['sourceFiles'] == source['sourceFiles'], f"trace source-file identity mismatch: {path}")
    ensure(prov['versions'] == source['versions'], f"trace/attempt runtime mismatch: {path}")
    ensure(prov['inputHash'] == fingerprint(prov['effectiveInputs']), f"bad input fingerprint: {path}")
    config = attempt['configuration']
    ensure(prov['populationSeed'] == config['populationSeed'] and prov['solverSeed'] == config['solverSeed'],
           f"trace/attempt seed mismatch: {path}")
    run = prov['effectiveInputs']['runConfig']
    ensure(run == {**config['run'], 'scenario': config['scenario'], 'seed': config['solverSeed']},
           f"trace/attempt run configuration mismatch: {path}")
    generator = prov['effectiveInputs']['generatorConfig']
    ensure(generator == {**config['generator'], 'short_list_policy': config['submission']['shortListPolicy']},
           f"trace/attempt generator configuration mismatch: {path}")
    ids = [s['id'] for s in trace['students']]
    ensure([[ids[j] for j in row] for row in prov['effectiveInputs']['submittedLists']] == trace['listed'],
           f"trace/input submission mismatch: {path}")
    return path


def _rewrite_evidence(evidence, old_parent, new_parent):
    evidence['path'] = os.path.relpath((old_parent / evidence['path']).resolve(), new_parent)


def assemble(inputs, output, *, partial=False, retained_source=False):
    output = Path(output).resolve()
    merged = {'schemaVersion': 2, **{name: [] for name in CATEGORIES}, 'attempts': [], 'batches': [],
              'meta': {}, 'assembly': {'inputs': [], 'missingInputs': [], 'partial': partial,
                                      'sourceVerification': 'retained_snapshot' if retained_source else 'current_working_tree'}}
    attempt_by_id, batch_by_id, sources = {}, {}, set()
    raw_rows = []
    for input_path in map(lambda x: Path(x).resolve(), inputs):
        if not input_path.exists():
            ensure(partial, f"missing experiment manifest: {input_path}")
            merged['assembly']['missingInputs'].append(str(input_path))
            continue
        raw = input_path.read_bytes()
        manifest = json.loads(raw)
        ensure(manifest.get('schemaVersion') == 2, f"not an attempt-ledger manifest: {input_path}")
        merged['assembly']['inputs'].append({'path': os.path.relpath(input_path, output.parent),
                                             'sha256': hashlib.sha256(raw).hexdigest(),
                                             'meta': manifest.get('meta', {})})
        if 'legacy' in manifest:
            merged.setdefault('legacyInputs', []).append({'path': str(input_path), 'legacy': manifest['legacy']})
        for original in manifest['attempts']:
            ensure(partial or original['status'] != 'running', f"unfinished attempt {original['id']} in {input_path}")
            verify_attempt(original, input_path, retained_source=retained_source)
            attempt = deepcopy(original)
            if attempt.get('traceEvidence'):
                _rewrite_evidence(attempt['traceEvidence'], input_path.parent, output.parent)
            previous = attempt_by_id.get(attempt['id'])
            ensure(previous is None or previous == attempt, f"conflicting duplicate attempt ID {attempt['id']}")
            if previous is None:
                attempt_by_id[attempt['id']] = attempt
                merged['attempts'].append(attempt)
                sources.add(attempt['source']['effectiveSourceHash'])
        for batch in manifest.get('batches', []):
            previous = batch_by_id.get(batch['id'])
            ensure(previous is None or previous == batch, f"conflicting duplicate batch ID {batch['id']}")
            if previous is None:
                batch_by_id[batch['id']] = deepcopy(batch)
                merged['batches'].append(deepcopy(batch))
        for category in CATEGORIES:
            for original in manifest.get(category, []):
                row = deepcopy(original)
                _rewrite_evidence(row['traceEvidence'], input_path.parent, output.parent)
                raw_rows.append((category, row))
    ensure(len(sources) <= 1, 'mixed effective source identities; analyze distinct revisions separately')
    used_rows = set()
    for category, row in raw_rows:
        attempt = attempt_by_id.get(row['attemptId'])
        ensure(attempt is not None and attempt['status'] == 'success', f"summary lacks successful attempt: {row['attemptId']}")
        ensure(row['fingerprint'] == attempt['fingerprint'] and row['traceEvidence'] == attempt['traceEvidence'],
               f"summary identity/evidence mismatch: {row['attemptId']}")
        ensure(row['evidenceStatus'] == 'verified_trace', f"unverified row in current evidence: {row['attemptId']}")
        ensure(category == attempt['category'], f"summary category mismatch: {row['attemptId']}")
        trace = json.loads((output.parent / attempt['traceEvidence']['path']).read_text())
        ensure(row['config'] == trace['config'], f"summary/trace configuration mismatch: {row['attemptId']}")
        for key, value in trace['summary'].items():
            ensure(row.get(key) == value, f"summary/trace statistic mismatch ({key}): {row['attemptId']}")
        for key, stat in (('pctExactly1ByRotation', 'pctExactly1'), ('metByRotation', 'meanDistinctMet'),
                          ('metRandomByRotation', 'meanDistinctMetRandom')):
            ensure(row[key] == [r['stats'][stat] for r in trace['rotations']],
                   f"summary/trace trajectory mismatch ({key}): {row['attemptId']}")
        ensure(row['leakageForcedEdges'] == trace['leakage']['forcedEdges'] and
               row['leakageStudents'] == trace['leakage']['studentsWithForcedEdge'],
               f"summary/trace leakage mismatch: {row['attemptId']}")
        ensure(row['fairness'] == trace['fairness'], f"summary/trace fairness mismatch: {row['attemptId']}")
        if (category, row['attemptId']) not in used_rows:
            merged[category].append(row)
            used_rows.add((category, row['attemptId']))
    ensure({a['id'] for a in merged['attempts'] if a['status'] == 'success'} == {r[1] for r in used_rows},
           'a successful attempt has no corresponding summary row')
    running = sum(a['status'] == 'running' for a in merged['attempts'])
    statuses = dict(Counter(a['status'] for a in merged['attempts']))
    completed = not running and not merged['assembly']['missingInputs']
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    merged['meta'] = {'assembledAt': now, 'attemptCount': len(merged['attempts']), 'terminalCounts': statuses,
                      'runningCount': running, 'successfulTraceCount': statuses.get('success', 0),
                      'effectiveSourceHashes': sorted(sources),
                      'status': 'completed' if completed else 'partial',
                      'scope': 'Only the listed attempts; historical summary-only evidence is excluded.'}
    if completed:
        merged['meta']['finished'] = now
    write_json(output, merged)
    return merged


def export_references(manifest, manifest_path, site_dir, *, seed=7):
    """Export a coherent six-scenario reference set, or leave the site intact."""
    selected = {}
    for attempt in manifest['attempts']:
        if attempt['status'] != 'success':
            continue
        cfg = attempt['configuration']
        run, gen = cfg['run'], cfg['generator']
        if (cfg['populationSeed'] == seed and cfg['solverSeed'] == seed and cfg['scenario'] in REFERENCES
                and run['rotations'] == 16 and run['first_state'] == 'mixed'
                and run['anneal_iters'] == 300_000 and run['cpsat_time'] == 3.5
                and run['workers'] == 8 and run['deterministic'] and run['feasibility_time'] == 20.0
                and gen['mu'] == 0.0 and gen['omega'] == 0.0 and gen['cross_grade_group_frac'] == 0.0
                and cfg['submission']['shortListPolicy'] == 'none'):
            selected[cfg['scenario']] = attempt
    missing = [name for name in REFERENCES if name not in selected]
    if missing:
        return {'status': 'waiting_for_complete_reference_set', 'missing': missing}
    manifest_path, site_dir = Path(manifest_path).resolve(), Path(site_dir).resolve()
    index = {'scenarios': [], 'seed': seed, 'evidenceStatus': 'verified_attempt_ledger'}
    identities = set()
    for name in REFERENCES:
        attempt = selected[name]
        path = manifest_path.parent / attempt['traceEvidence']['path']
        raw = path.read_bytes()
        ensure(hashlib.sha256(raw).hexdigest() == attempt['traceEvidence']['sha256'], f"changed reference trace: {path}")
        trace = json.loads(raw)
        atomic_bytes(site_dir / (name + '.json'), raw)
        identities.add(attempt['source']['effectiveSourceHash'])
        index['scenarios'].append({'name': name, 'file': name + '.json', 'title': trace['config']['title'],
                                   'short': trace['config']['short'], 'summary': trace['summary'], 'bytes': len(raw),
                                   'sha256': attempt['traceEvidence']['sha256'], 'attemptId': attempt['id'],
                                   'fingerprint': attempt['fingerprint']})
    site_manifest = {'scenarios': list(REFERENCES), 'seed': seed, 'rotations': 16,
                     'playback': 'precomputed validated solver traces',
                     'effectiveSourceHashes': sorted(identities),
                     'evidenceStatus': 'verified_attempt_ledger',
                     'evidenceManifestSha256': digest(manifest_path),
                     'attemptIds': {name: selected[name]['id'] for name in REFERENCES}}
    write_json(site_dir / 'index.json', index)
    write_json(site_dir / 'manifest.json', site_manifest)
    return {'status': 'exported', 'scenarios': list(REFERENCES), 'siteDir': str(site_dir)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--inputs', nargs='+', type=Path, default=DEFAULT_INPUTS)
    ap.add_argument('--out', type=Path, default=ROOT / 'results' / 'verified_experiments.json')
    ap.add_argument('--partial', action='store_true')
    ap.add_argument('--retained-source', action='store_true',
                    help='verify source bytes in results/source_snapshots/HASH, allowing later working-tree repairs')
    ap.add_argument('--no-site', action='store_true')
    ap.add_argument('--site-dir', type=Path, default=ROOT / 'docs' / 'data')
    ap.add_argument('--site-seed', type=int, default=7)
    args = ap.parse_args(argv)
    merged = assemble(args.inputs, args.out, partial=args.partial, retained_source=args.retained_source)
    status = {'output': str(args.out), **merged['meta']}
    if not args.no_site:
        status['siteExport'] = export_references(merged, args.out, args.site_dir, seed=args.site_seed)
    print(json.dumps(status, indent=2))
    return merged


if __name__ == '__main__':
    main()
