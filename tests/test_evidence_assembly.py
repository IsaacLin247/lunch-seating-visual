"""Publication assembly must retain failures and verify every numerical record."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('assemble_evidence', ROOT / 'paper' / 'assemble_evidence.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def real_attempt(tmp_path):
    # This fixture inspects an already retained chart; it never reruns a solver.
    manifest_path = ROOT / 'results' / 'verified_core_b.json'
    if not manifest_path.exists():
        pytest.skip('requires retained verified experiment fixture')
    manifest = json.loads(manifest_path.read_text())
    source = next((a for a in manifest['attempts'] if a['status'] == 'success'), None)
    if source is None:
        pytest.skip('requires one successful retained experiment')
    attempt = copy.deepcopy(source)
    trace_path = manifest_path.parent / attempt['traceEvidence']['path']
    (tmp_path / 'trace.json').write_bytes(trace_path.read_bytes())
    attempt['traceEvidence']['path'] = 'trace.json'
    summary = copy.deepcopy(next(row for row in manifest[attempt['category']] if row['attemptId'] == attempt['id']))
    summary['traceEvidence']['path'] = 'trace.json'
    data = {'schemaVersion': 2, 'attempts': [attempt], 'batches': [], 'meta': {},
            **{name: [summary] if name == attempt['category'] else [] for name in MODULE.CATEGORIES}}
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(data))
    return path, data


def test_running_attempt_requires_partial_and_denominator_is_retained(real_attempt, tmp_path):
    path, data = real_attempt
    interrupted = copy.deepcopy(data['attempts'][0])
    interrupted.update(id='unfinished-example', status='interrupted_unfinished')
    interrupted.pop('traceEvidence')
    running = copy.deepcopy(interrupted)
    running.update(id='running-example', status='running')
    data['attempts'].extend([interrupted, running])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unfinished attempt'):
        MODULE.assemble([path], tmp_path / 'merged.json', retained_source=True)
    merged = MODULE.assemble([path], tmp_path / 'merged.json', partial=True, retained_source=True)
    assert merged['meta']['attemptCount'] == 3
    assert merged['meta']['terminalCounts'] == {'success': 1, 'interrupted_unfinished': 1, 'running': 1}
    assert merged['meta']['status'] == 'partial' and 'finished' not in merged['meta']


def test_assembly_refuses_tampered_retained_trace(real_attempt, tmp_path):
    path, _ = real_attempt
    (tmp_path / 'trace.json').write_text('{}')
    with pytest.raises(ValueError, match='missing or changed trace evidence'):
        MODULE.assemble([path], tmp_path / 'merged.json', retained_source=True)


def test_assembly_refuses_wrong_requested_configuration_even_with_recomputed_key(real_attempt, tmp_path):
    path, data = real_attempt
    attempt = data['attempts'][0]
    attempt['configuration']['run']['rotations'] = 5
    attempt['fingerprint'] = MODULE.fingerprint({
        'configuration': {'category': attempt['category'], **attempt['configuration']},
        'effectiveSourceHash': attempt['source']['effectiveSourceHash'], 'versions': attempt['source']['versions']})
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='run configuration mismatch'):
        MODULE.assemble([path], tmp_path / 'merged.json', retained_source=True)


def test_reference_export_does_not_publish_an_incomplete_scenario_set(real_attempt, tmp_path):
    path, _ = real_attempt
    merged = MODULE.assemble([path], tmp_path / 'merged.json', retained_source=True)
    site = tmp_path / 'site'
    result = MODULE.export_references(merged, tmp_path / 'merged.json', site)
    assert result['status'] == 'waiting_for_complete_reference_set'
    assert not site.exists()


def test_assembly_refuses_a_cached_headline_different_from_full_trace(real_attempt, tmp_path):
    path, data = real_attempt
    category = data['attempts'][0]['category']
    data[category][0]['pctExactly1Mean'] = -1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='statistic mismatch'):
        MODULE.assemble([path], tmp_path / 'merged.json', retained_source=True)


def test_unavailable_evidence_stays_in_denominator_without_being_claimed_verified(real_attempt, tmp_path):
    path, data = real_attempt
    old = copy.deepcopy(data['attempts'][0])
    old.update(id='lost-evidence', status='evidence_unavailable', originalTerminalStatus='success')
    old['traceEvidence']['path'] = 'missing-trace.json'
    data['attempts'].append(old)
    path.write_text(json.dumps(data))
    result = MODULE.assemble([path], tmp_path / 'merged.json', retained_source=True)
    assert result['meta']['attemptCount'] == 2
    assert result['meta']['terminalCounts'] == {'success': 1, 'evidence_unavailable': 1}
    assert result['meta']['successfulTraceCount'] == 1
