import hashlib
import json

import pytest


@pytest.fixture
def graduation_request(tmp_path):
    path = tmp_path / 'request.json'
    path.write_text(json.dumps({'schema_version': 1, 'request_id': 'tiny-v1',
        'num_machines': 1, 'tasks': [{'job_id': 0, 'processing_time': 2, 'due_date': 2},
                                   {'job_id': 1, 'processing_time': 2, 'due_date': 4}],
        'maintenance': [{'machine_id': 0, 'duration': 2, 'window_start': 0, 'window_end': 6, 'fixed_start': 0}],
        'solver': {'time_limit': 2.0, 'num_workers': 1, 'seed': 42}}), encoding='utf-8')
    return path


@pytest.mark.parametrize('fault', ['extra', 'bool', 'nan', 'window', 'missing_fixed', 'time', 'threads', 'duplicate'])
def test_request_rejects_unsupported_or_unbounded_inputs(graduation_request, fault):
    from src.ai_workflow.graduation_backend import describe_graduation_request
    raw = json.loads(graduation_request.read_text())
    if fault == 'extra': raw['transport_time'] = 2
    if fault == 'bool': raw['tasks'][0]['processing_time'] = True
    if fault == 'nan': raw['solver']['time_limit'] = float('nan')
    if fault == 'window': raw['maintenance'][0]['window_end'] = 1
    if fault == 'missing_fixed': raw['maintenance'][0].pop('fixed_start')
    if fault == 'time': raw['solver']['time_limit'] = 31
    if fault == 'threads': raw['solver']['num_workers'] = 5
    text = json.dumps(raw)
    if fault == 'duplicate': text = text.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    graduation_request.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError): describe_graduation_request(graduation_request)


def test_real_fixed_joint_backend_and_saved_artifacts_revalidate(graduation_request, tmp_path):
    from src.ai_workflow.graduation_backend import describe_graduation_request, run_graduation_request, verify_graduation_artifacts
    description = describe_graduation_request(graduation_request)
    output = tmp_path / 'out'
    manifest = run_graduation_request(graduation_request, output, expected_request_hash=description['request_hash'])
    assert manifest['status'] == 'COMPLETED' and manifest['accepted_runs'] == 2
    assert manifest['results']['fixed']['total_tardiness'] == 4
    assert manifest['results']['joint']['total_tardiness'] == 0
    digest = hashlib.sha256((output / 'manifest.json').read_bytes()).hexdigest()
    assert verify_graduation_artifacts(output, digest) == manifest
    with pytest.raises(FileExistsError): run_graduation_request(graduation_request, output, expected_request_hash=description['request_hash'])
    with pytest.raises(ValueError): run_graduation_request(graduation_request, tmp_path / 'wrong', expected_request_hash='0'*64)


@pytest.mark.parametrize('target', ['manifest.json', 'fixed.json', 'request.json', 'report.md'])
def test_artifact_changes_reject_previously_reviewed_results(graduation_request, tmp_path, target):
    from src.ai_workflow.graduation_backend import describe_graduation_request, run_graduation_request, verify_graduation_artifacts
    output = tmp_path / 'out'
    run_graduation_request(graduation_request, output,
                          expected_request_hash=describe_graduation_request(graduation_request)['request_hash'])
    digest = hashlib.sha256((output / 'manifest.json').read_bytes()).hexdigest()
    (output / target).write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError): verify_graduation_artifacts(output, digest)


@pytest.mark.parametrize('fault', ['missing_maintenance', 'objective', 'raised', 'feasible'])
def test_backend_rechecks_domain_metadata_and_preserves_feasible_status(graduation_request, tmp_path, monkeypatch, fault):
    from src.ai_workflow import graduation_backend as module
    original = module.solve_parallel_maintenance
    def altered(*a, **kw):
        if fault == 'raised': raise RuntimeError('test solver failure')
        result = original(*a, **kw)
        if fault == 'missing_maintenance': result.maintenance_records.clear()
        if fault == 'objective': result.solver_objective_value += 1
        if fault == 'feasible': result.solver_status = 'FEASIBLE'
        return result
    monkeypatch.setattr(module, 'solve_parallel_maintenance', altered)
    result = module.run_graduation_request(graduation_request, tmp_path / 'out',
        expected_request_hash=module.describe_graduation_request(graduation_request)['request_hash'])
    if fault == 'feasible':
        assert result['status'] == 'COMPLETED'
        assert all(row['solver_status'] == 'FEASIBLE' for row in result['results'].values())
    else:
        assert result['status'] == 'FAILED' and result['accepted_runs'] == 0
        assert all(row['total_tardiness'] is None for row in result['results'].values())
