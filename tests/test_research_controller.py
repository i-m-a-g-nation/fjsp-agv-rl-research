"""Controller invariants; worker execution is replaced only in orchestration tests."""

import json
from pathlib import Path
import subprocess
import sqlite3
import time
import copy

import pytest

from src.ai_workflow import research_controller as controller
from src.ai_workflow import research_tasks as tasks


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'experiments/results/exp_026_validation_iteration_phase1_v2'
PAPER = ROOT / 'experiments/results/exp_023_state_semantic_v1'


@pytest.fixture(scope='session')
def diagnostic_report():
    from src.graduation.permutation_diagnostics import diagnose_permutations
    return diagnose_permutations(REFERENCE)


@pytest.fixture
def workers(monkeypatch, diagnostic_report):
    calls = []

    def run(script, payload, timeout):
        assert timeout > 0
        calls.append(payload['task_id'])
        if payload['task_id'] == 'audit_paper_evidence':
            return tasks.audit_paper(PAPER)
        return diagnostic_report

    monkeypatch.setattr(controller, 'supervised_json_process', run)
    return calls


def test_one_start_dispatches_two_tasks_and_stops_from_new_evidence(tmp_path, workers):
    state = controller.run_controller(tmp_path / 'batch')
    assert workers == ['audit_paper_evidence', 'diagnose_identifier_permutations']
    assert state['status'] == 'STOPPED'
    assert state['stop_reason'] == 'implementation_required'
    assert state['next_task']['id'] == 'design_shared_scorer_candidate'
    assert state['skipped_candidates'] == ['running_mean']
    assert all(track['research_status'] == 'not_achieved' for track in state['tracks'].values())
    assert state['budget']['provider_calls'] == 0
    assert state['budget']['active_seconds_reserved'] == 0
    assert len(state['decisions']) >= 3
    assert all(item['result_sha256'] for item in state['tasks'])


def test_slice_resume_and_terminal_resume_do_not_repeat_or_reset_budget(tmp_path, workers):
    folder = tmp_path / 'batch'
    first = controller.run_controller(folder, steps=1)
    assert first['status'] == 'YIELDED'
    second = controller.run_controller(folder)
    assert len(workers) == 2
    assert second['budget']['active_seconds'] >= first['budget']['active_seconds']
    final = controller.run_controller(folder)
    assert len(workers) == 2
    assert final['budget'] == second['budget']


def test_result_tampering_and_changed_limits_refuse_resume(tmp_path, workers):
    folder = tmp_path / 'batch'
    controller.run_controller(folder, steps=1)
    with pytest.raises(ValueError, match='identity|configuration'):
        controller.run_controller(folder, max_active_seconds=121)
    (folder / 'task_01.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='result'):
        controller.run_controller(folder)
    assert len(workers) == 1


def test_source_and_input_changes_refuse_resume(tmp_path, workers, monkeypatch):
    folder = tmp_path / 'batch'
    controller.run_controller(folder, steps=1)
    monkeypatch.setattr(controller, '_source_hashes', lambda: {'changed': 'hash'})
    with pytest.raises(ValueError, match='identity'):
        controller.run_controller(folder)
    assert len(workers) == 1


def test_crash_does_not_refund_reservation_or_restart_task(tmp_path, workers):
    folder = tmp_path / 'batch'
    controller.run_controller(folder, steps=1)
    state_path = folder / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    state['status'] = 'RUNNING'
    state['tasks'].append({'id': 'diagnose_identifier_permutations', 'status': 'RUNNING'})
    state_path.write_text(json.dumps(state), encoding='utf-8')
    limits = controller.BudgetLimits(120, 0, 0)
    budget = controller.RunBudget(folder / 'budget.sqlite', limits)
    budget.reserve_active_segment()
    result = controller.run_controller(folder)
    assert result['status'] == 'STOPPED'
    assert result['stop_reason'] == 'interrupted_task'
    assert result['budget']['active_seconds_reserved'] > 0
    assert len(workers) == 1


def test_timeout_fails_closed_and_never_auto_retries(tmp_path, monkeypatch):
    calls = []

    def timeout(*args, **kwargs):
        calls.append(True)
        raise subprocess.TimeoutExpired('worker', 1)

    monkeypatch.setattr(controller, 'supervised_json_process', timeout)
    folder = tmp_path / 'batch'
    result = controller.run_controller(folder)
    assert result['stop_reason'] == 'task_timeout'
    assert result['tasks'][0]['error_type'] == 'TimeoutExpired'
    controller.run_controller(folder)
    assert len(calls) == 1


def test_malformed_worker_result_cannot_advance(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, 'supervised_json_process', lambda *a, **k: {'status': 'COMPLETED'})
    result = controller.run_controller(tmp_path / 'batch')
    assert result['stop_reason'] == 'task_failed'
    assert result['tasks'][0]['status'] == 'FAILED'


def test_task_cap_and_innovation_scope_boundary(tmp_path, workers):
    capped = controller.run_controller(tmp_path / 'capped', max_tasks=1)
    assert capped['stop_reason'] == 'task_count_budget'
    assert len(workers) == 1
    innovation = controller.run_controller(tmp_path / 'innovation', track='innovation')
    assert innovation['stop_reason'] == 'no_registered_innovation_executor'
    assert len(workers) == 1


@pytest.mark.parametrize('field,value', [('max_tasks', True), ('max_tasks', 3), ('steps', 0),
                                       ('track', 'unknown'), ('max_active_seconds', float('nan'))])
def test_bad_configuration_is_rejected_before_execution(tmp_path, workers, field, value):
    with pytest.raises(ValueError):
        controller.run_controller(tmp_path / 'batch', **{field: value})
    assert workers == []


def test_lock_refuses_second_writer(tmp_path, workers):
    folder = tmp_path / 'batch'
    folder.mkdir()
    with controller._exclusive_lock(folder):
        with pytest.raises(ValueError, match='running'):
            controller.run_controller(folder)
    assert workers == []


def test_actual_evidence_audit_preserves_unapproved_partial_source_status():
    observation = tasks.inspect_inputs(REFERENCE, PAPER)
    assert observation['rejected_candidates'] == ['running_mean']
    assert observation['means']['fixed'] == {'none': 10.25, 'running_mean': 11.875}
    result = tasks.execute_task('audit_paper_evidence', REFERENCE, PAPER)
    assert result['claims_located'] == 2
    assert result['human_approval'] is False
    assert result['complete_source_bundle'] is False
    assert result['full_pdf_reverified'] is False
    assert result['research_status'] == 'not_achieved'


def test_registry_rejects_document_commands():
    with pytest.raises(ValueError, match='registered'):
        tasks.execute_task('python dangerous.py', REFERENCE, PAPER)


def test_partial_or_overlapping_output_folder_refused(tmp_path, workers):
    folder = tmp_path / 'partial'
    folder.mkdir()
    (folder / 'unrelated.txt').write_text('retain', encoding='utf-8')
    with pytest.raises(ValueError, match='empty'):
        controller.run_controller(folder)
    with pytest.raises(ValueError, match='overlap'):
        controller.run_controller(REFERENCE / 'new_controller')
    assert workers == []


def test_missing_or_empty_budget_never_reinitializes_on_resume(tmp_path, workers):
    folder = tmp_path / 'batch'
    controller.run_controller(folder, steps=1)
    (folder / 'budget.sqlite').unlink()
    with pytest.raises(ValueError, match='budget'):
        controller.run_controller(folder)
    (folder / 'budget.sqlite').write_bytes(b'')
    with pytest.raises(ValueError, match='budget'):
        controller.run_controller(folder)
    assert len(workers) == 1


def test_deleted_budget_row_cannot_reset_spend(tmp_path, workers):
    folder = tmp_path / 'batch'
    controller.run_controller(folder, steps=1)
    connection = sqlite3.connect(folder / 'budget.sqlite')
    with connection:
        connection.execute('DELETE FROM workflow_budget WHERE id=1')
    connection.close()
    with pytest.raises(ValueError, match='budget'):
        controller.run_controller(folder)
    assert len(workers) == 1


def test_active_budget_includes_nonterminal_identity_preflight(tmp_path, workers, monkeypatch):
    original = controller._source_hashes

    def delayed():
        time.sleep(.15)
        return original()

    monkeypatch.setattr(controller, '_source_hashes', delayed)
    result = controller.run_controller(tmp_path / 'batch', max_active_seconds=.1)
    assert workers == []
    assert result['stop_reason'] == 'active_time_budget'
    assert result['budget']['active_seconds'] >= .15
    resumed = controller.run_controller(tmp_path / 'batch', max_active_seconds=.1)
    assert resumed['stop_reason'] == 'active_time_budget'
    assert resumed['budget'] == result['budget']


@pytest.mark.parametrize('value', [
    {'kind': 'validation_only_permutation_diagnosis', 'status': 'COMPLETED',
     'research_status': 'not_achieved', 'probe_evaluated': False, 'final_test_evaluated': False,
     'sensitive_states': 999999, 'training_performed': True},
    {'kind': 'archived_paper_evidence_audit', 'status': 'COMPLETED',
     'research_status': 'not_achieved', 'human_approval': False, 'complete_source_bundle': False,
     'full_pdf_reverified': True, 'author_code_reexecuted': True, 'claims_located': -1},
])
def test_contradictory_or_incomplete_results_are_rejected(value):
    task_id = next(key for key, kind in tasks.TASK_KINDS.items() if kind == value['kind'])
    with pytest.raises(ValueError):
        tasks.validate_task_result(task_id, value)


def test_truncated_states_cannot_redefine_the_native_denominator(diagnostic_report):
    result = copy.deepcopy(diagnostic_report)
    for case in result['cases']:
        case['states'] = case['states'][:1]
    sensitive = sum(s['sensitive'] for c in result['cases'] for s in c['states'])
    result['sensitive_states'] = result['aggregate']['sensitive_states'] = sensitive
    result['denominators'].update(expected_state_comparisons=64, state_comparisons=64)
    with pytest.raises(ValueError):
        tasks.validate_task_result('diagnose_identifier_permutations', result)


def test_controlled_profile_dispatches_package_gate_and_comparison(tmp_path, monkeypatch, diagnostic_report):
    calls = []
    def local_worker(script, payload, timeout):
        calls.append(payload['task_id'])
        if payload['task_id'] == 'diagnose_identifier_permutations':
            return diagnostic_report
        return tasks.execute_task(payload['task_id'], payload['reference_archive'], payload['paper_archive'],
                                  expected_inputs=payload['expected_inputs'], batch_dir=payload['batch_dir'])
    monkeypatch.setattr(controller, 'supervised_json_process', local_worker)
    folder = tmp_path / 'controlled'
    state = controller.run_controller(folder, profile='shared_scorer_v1')
    assert state['stop_reason'] == 'candidate_round_complete'
    assert calls == ['audit_paper_evidence', 'diagnose_identifier_permutations', 'materialize_shared_scorer',
                     'check_shared_scorer', 'compare_shared_scorer']
    assert len(state['tasks']) == 5
    assert (folder / 'candidate/candidate.patch').is_file()
    assert state['next_task']['executable'] is False
    assert state['next_task']['selected_methods'] == {'fixed': 'none', 'joint': 'none'}
    assert state['research_status'] == 'not_achieved'
    saved = list(calls)
    resumed = controller.run_controller(folder, profile='shared_scorer_v1')
    assert calls == saved and resumed['budget'] == state['budget']
    (folder / 'candidate/policy.py').write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='identity|template'):
        controller.run_controller(folder, profile='shared_scorer_v1')


def test_audit_profile_does_not_enable_candidate_tasks_and_bad_profile_is_rejected(tmp_path, workers):
    with pytest.raises(ValueError, match='profile'):
        controller.run_controller(tmp_path / 'bad', profile='arbitrary_code')
    state = controller.run_controller(tmp_path / 'audit')
    assert len(state['tasks']) == 2 and state['stop_reason'] == 'implementation_required'
