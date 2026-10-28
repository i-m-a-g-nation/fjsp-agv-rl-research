"""A development pilot cannot conceal missing rows or accept invented optima."""
import json
from pathlib import Path
import subprocess

import pytest

from src.graduation import reference_pilot as pilot
from src.graduation.reference_protocol import build_pilot_cases


@pytest.fixture(scope='module')
def completed(tmp_path_factory):
    folder = tmp_path_factory.mktemp('reference-pilot')/'run'
    result = pilot.run_pilot(folder)
    assert result['status'] == 'COMPLETED'
    return folder


def test_native_complete_pilot_rechecks_every_saved_plan(completed):
    result = pilot.recheck_pilot(completed)
    assert result['validated_runs'] == 24
    assert result['paired_cases'] == 12
    assert result['base_workloads'] == 3
    assert result['research_status'] == 'not_achieved'
    assert result['formal_approval'] is False
    assert result['model_calls'] == result['network_calls'] == 0
    assert sum(p['fixed_total_tardiness'] == 0 for p in result['pairs']) >= 1
    for pair in result['pairs']:
        assert pair['joint_total_tardiness'] <= pair['fixed_total_tardiness']
        assert pair['relative_improvement'] is None if pair['fixed_total_tardiness'] == 0 else True


def test_existing_directory_never_restarts(completed):
    before = {p.relative_to(completed):p.read_bytes() for p in completed.rglob('*') if p.is_file()}
    with pytest.raises(FileExistsError):
        pilot.run_pilot(completed)
    assert before == {p.relative_to(completed):p.read_bytes() for p in completed.rglob('*') if p.is_file()}


@pytest.mark.parametrize('seconds', [True, 0, -1, 90.1, float('nan'), float('inf')])
def test_invalid_budget_rejected_before_creating_folder(tmp_path, seconds):
    with pytest.raises(ValueError):
        pilot.run_pilot(tmp_path/'invalid', max_active_seconds=seconds)
    assert not (tmp_path/'invalid').exists()


@pytest.mark.parametrize('error', [subprocess.TimeoutExpired('worker', 0.01), RuntimeError('worker failed')])
def test_worker_failure_retains_all_planned_rows(tmp_path, monkeypatch, error):
    def stopped(*args, **kwargs):
        raise error
    monkeypatch.setattr(pilot, 'supervised_json_process', stopped)
    result = pilot.run_pilot(tmp_path/'failed')
    expected = 'BUDGET_EXHAUSTED' if isinstance(error, subprocess.TimeoutExpired) else 'FAILED'
    assert result['status'] == expected
    state = json.loads((tmp_path/'failed/state.json').read_text())
    assert len(state['rows']) == 24
    assert all(row['status'] == 'NOT_RUN' and row['total_tardiness'] is None for row in state['rows'])
    assert len(list((tmp_path/'failed/inputs').glob('*.json'))) == 12
    with pytest.raises(ValueError):
        pilot.recheck_pilot(tmp_path/'failed')


def test_claimed_worker_completion_without_results_cannot_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, 'supervised_json_process', lambda *a, **k:{'status':'COMPLETED'})
    assert pilot.run_pilot(tmp_path/'empty')['status'] == 'FAILED'


def test_changed_input_is_rejected(completed, tmp_path):
    import shutil
    folder = tmp_path/'changed'
    shutil.copytree(completed, folder)
    source = next((folder/'inputs').glob('*.json'))
    value = json.loads(source.read_text())
    value['data']['tasks'][0]['due_date'] += 1
    source.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        pilot.recheck_pilot(folder)


def test_forged_optimum_rejected_by_fresh_oracle(completed, tmp_path):
    import shutil
    folder = tmp_path/'forged'
    shutil.copytree(completed, folder)
    case = build_pilot_cases()[0]
    trace_path = folder/'schedules'/f"{case['case_id']}-fixed.json"
    trace = json.loads(trace_path.read_text())
    # A self-consistent hash ledger cannot substitute for the actual plan metric.
    trace['candidate']['total_tardiness'] += 1
    trace_path.write_bytes(pilot.encoded(trace))
    manifest_path = folder/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['artifacts'][trace_path.relative_to(folder).as_posix()] = pilot.file_sha(trace_path)
    manifest_path.write_bytes(pilot.encoded(manifest))
    with pytest.raises(ValueError):
        pilot.recheck_pilot(folder)


def test_bad_mode_oracle_and_feasible_status_never_validate(monkeypatch):
    case = build_pilot_cases()[0]
    real = pilot.solve_parallel_maintenance
    def merely_feasible(*args, **kwargs):
        result = real(*args, **kwargs)
        result.solver_status = 'FEASIBLE'
        return result
    monkeypatch.setattr(pilot, 'solve_parallel_maintenance', merely_feasible)
    trace = pilot.solve_case(case, 'fixed')
    assert trace['status'] == 'FAILED'
    assert trace['total_tardiness'] is None


@pytest.mark.parametrize('damage', ['over_budget','negative_time','wrong_count','false_approval'])
def test_rehashed_summary_cannot_change_execution_contract(completed, tmp_path, damage):
    import shutil
    folder = tmp_path/damage
    shutil.copytree(completed, folder)
    summary = json.loads((folder/'summary.json').read_text())
    field, value = {'over_budget':('active_seconds',91), 'negative_time':('active_seconds',-1),
        'wrong_count':('finished_rows',23), 'false_approval':('formal_approval',True)}[damage]
    summary[field] = value
    (folder/'summary.json').write_bytes(pilot.encoded(summary))
    manifest = json.loads((folder/'manifest.json').read_text())
    manifest['artifacts']['summary.json'] = pilot.file_sha(folder/'summary.json')
    (folder/'manifest.json').write_bytes(pilot.encoded(manifest))
    with pytest.raises(ValueError):
        pilot.recheck_pilot(folder)


def test_final_receipt_io_cannot_authorize_expired_success(tmp_path, monkeypatch):
    original_write, original_clock = pilot._write, pilot.time.monotonic
    delay = [0]
    def slow_summary(path, value):
        original_write(path, value)
        if Path(path).name == 'summary.json':
            delay[0] = 100
    monkeypatch.setattr(pilot, '_write', slow_summary)
    monkeypatch.setattr(pilot.time, 'monotonic', lambda:original_clock()+delay[0])
    result = pilot.run_pilot(tmp_path/'slow-finalize')
    assert result['status'] == 'BUDGET_EXHAUSTED'
    assert json.loads((tmp_path/'slow-finalize/manifest.json').read_text())['status'] == 'BUDGET_EXHAUSTED'


def test_interrupted_worker_preserves_completed_and_unstarted_rows(tmp_path, monkeypatch):
    def interrupted(script, payload, timeout):
        folder = Path(payload['folder'])
        state = json.loads((folder/'state.json').read_text())
        case = build_pilot_cases()[0]
        trace = pilot.solve_case(case, 'fixed')
        pilot._write(folder/'schedules'/f"{case['case_id']}-fixed.json", trace)
        state['rows'][0].update(status='PASS',total_tardiness=trace['total_tardiness'])
        state['rows'][1]['status'] = 'RUNNING'
        pilot._write(folder/'state.json', state)
        raise subprocess.TimeoutExpired('worker', timeout)
    monkeypatch.setattr(pilot, 'supervised_json_process', interrupted)
    folder = tmp_path/'partial'
    result = pilot.run_pilot(folder)
    rows = json.loads((folder/'state.json').read_text())['rows']
    assert result['status'] == 'BUDGET_EXHAUSTED' and result['finished_rows'] == 1
    assert [r['status'] for r in rows] == ['PASS','INTERRUPTED']+['NOT_RUN']*22
    assert rows[1]['total_tardiness'] is None


@pytest.mark.parametrize('field,value', [('version',999),('source_hashes',{}),('runtime',{})])
def test_missing_or_unknown_provenance_schema_is_rejected(completed, tmp_path, field, value):
    import shutil
    folder = tmp_path/'provenance'
    shutil.copytree(completed, folder)
    manifest = json.loads((folder/'manifest.json').read_text())
    manifest[field] = value
    (folder/'manifest.json').write_bytes(pilot.encoded(manifest))
    with pytest.raises(ValueError):
        pilot.recheck_pilot(folder)


def test_source_equality_is_explicit_for_portable_evidence(completed, tmp_path):
    import shutil
    assert pilot.recheck_pilot(completed, require_current_sources=True)['current_sources_checked']
    folder = tmp_path/'other-sources'
    shutil.copytree(completed, folder)
    manifest = json.loads((folder/'manifest.json').read_text())
    manifest['source_hashes']['src/graduation/solver.py'] = '0'*64
    (folder/'manifest.json').write_bytes(pilot.encoded(manifest))
    assert pilot.recheck_pilot(folder)['current_sources_checked'] is False
    with pytest.raises(ValueError):
        pilot.recheck_pilot(folder, require_current_sources=True)
