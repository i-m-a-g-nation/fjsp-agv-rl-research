"""Only verified rejected-candidate evidence can authorize the single next trial."""
from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'experiments/results/exp_027_controlled_candidate_v1'
REFERENCE = ROOT / 'experiments/results/exp_026_validation_iteration_v1'


def api():
    return importlib.import_module('src.ai_workflow.candidate_feedback')


def test_saved_negative_candidate_is_diagnosed_by_actual_checkpoint_replay():
    # A pure diagnostic core also supports historical read-only analysis. The
    # registered executor separately requires a current bound completed receipt.
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    result = json.loads((ARCHIVE / 'candidate_run/results.json').read_bytes())
    report = api().analyse_comparison(ARCHIVE, REFERENCE, result, SharedScorer)
    assert report['counts'] == {'training_runs': 4, 'training_updates': 256,
        'checked_plans': 80, 'same_state_comparisons': 96, 'validation_checkpoints': 20}
    assert [r['changed_updates'] for r in report['runs']] == [61, 63, 55, 54]
    assert [r['same_state_argmax_changes'] for r in report['runs']] == [0, 0, 0, 2]
    assert [r['greedy_plans_changed'] for r in report['runs']] == [0, 0, 0, 2]
    assert report['hypothesis']['eligible'] is True
    assert report['hypothesis']['learning_rate'] == .1
    assert report['hypothesis']['causal_claim'] is False
    assert report['training_performed'] is False


@pytest.mark.parametrize('damage', ['updated_false', 'clipped', 'rank_changed', 'retained', 'not_flat', 'no_probability_change'])
def test_ineligible_diagnostics_do_not_authorize_a_retry(damage):
    rows = [{'changed_updates': 60, 'clipped_updates': 0, 'parameter_l2_change': .1,
             'max_probability_change': .01, 'same_state_argmax_changes': 0,
             'greedy_plans_changed': 0, 'flat_validation': True} for _ in range(4)]
    decisions = {m: {'selected_method': 'none'} for m in ('fixed', 'joint')}
    if damage == 'updated_false':
        for row in rows: row['changed_updates'] = 0
    if damage == 'clipped': rows[-1]['clipped_updates'] = 1
    if damage == 'rank_changed':
        for row in rows: row['same_state_argmax_changes'] = 1
    if damage == 'retained': decisions['fixed']['selected_method'] = 'shared_scorer_v1'
    if damage == 'not_flat':
        for row in rows: row['flat_validation'] = False
    if damage == 'no_probability_change':
        for row in rows: row['max_probability_change'] = 0.
    assert api().step_hypothesis(rows, decisions)['eligible'] is False


@pytest.mark.parametrize('damage', ['missing_run', 'wrong_log', 'wrong_selected_plan', 'wrong_checkpoint'])
def test_partial_or_self_inconsistent_diagnostic_evidence_fails(damage):
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    report = json.loads((ARCHIVE / 'candidate_run/results.json').read_bytes())
    if damage == 'missing_run': report['training_runs'].pop()
    if damage == 'wrong_log': report['training_runs'][0]['logs'][0]['update']['changed'] = False
    if damage == 'wrong_selected_plan': report['candidate_rows'][0]['actions'] = []
    if damage == 'wrong_checkpoint': report['training_runs'][0]['checkpoints']['final']['sha256'] = '0'*64
    with pytest.raises(ValueError):
        api().analyse_comparison(ARCHIVE, REFERENCE, report, SharedScorer)


def test_diagnostic_budget_interrupts_without_claiming_success():
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    result = json.loads((ARCHIVE / 'candidate_run/results.json').read_bytes())
    def exhausted(): raise TimeoutError('diagnostic cap')
    with pytest.raises(TimeoutError, match='cap'):
        api().analyse_comparison(ARCHIVE, REFERENCE, result, SharedScorer, check_budget=exhausted)


def test_feedback_planner_branches_from_verified_new_results_and_stops_after_one_trial():
    from src.ai_workflow.research_tasks import choose_next
    observation = {'rejected_candidates': ['running_mean']}
    completed = {t: {} for t in ('audit_paper_evidence', 'materialize_shared_scorer', 'check_shared_scorer')}
    completed['diagnose_identifier_permutations'] = {'sensitive_states': 1}
    completed['compare_shared_scorer'] = {'decisions': {m: {'selected_method': 'none'} for m in ('fixed', 'joint')}}
    def choose(profile='shared_scorer_feedback_v1'):
        return choose_next(observation, completed, track='graduation', profile=profile)
    assert choose('shared_scorer_v1')['stop_reason'] == 'candidate_round_complete'
    assert choose()['task_id'] == 'diagnose_rejected_candidate'
    completed['diagnose_rejected_candidate'] = {'hypothesis': {'eligible': False}}
    assert choose()['stop_reason'] == 'feedback_no_registered_trial'
    completed['diagnose_rejected_candidate']['hypothesis']['eligible'] = True
    assert choose()['task_id'] == 'compare_larger_step'
    completed['compare_larger_step'] = deepcopy(completed['compare_shared_scorer'])
    assert choose()['stop_reason'] == 'feedback_round_complete'
    assert choose()['next_task']['executable'] is False


@pytest.fixture(scope='module')
def completed_feedback(tmp_path_factory, untraced_wall_clock):
    from src.ai_workflow import research_controller as controller, research_tasks as tasks
    folder = tmp_path_factory.mktemp('feedback') / 'batch'
    calls = []
    def worker(script, payload, timeout):
        calls.append(payload['task_id'])
        return tasks.execute_task(payload['task_id'], payload['reference_archive'], payload['paper_archive'],
                                  expected_inputs=payload['expected_inputs'], batch_dir=payload['batch_dir'])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(controller, 'supervised_json_process', worker)
        with untraced_wall_clock():
            first = controller.run_controller(folder, profile='shared_scorer_feedback_v1', steps=5)
            assert first['status'] == 'YIELDED', first
            assert len(first['tasks']) == 5
            second = controller.run_controller(folder, profile='shared_scorer_feedback_v1', steps=1)
            assert second['status'] == 'YIELDED', second
            assert second['next_task']['task_id'] == 'compare_larger_step'
            final = controller.run_controller(folder, profile='shared_scorer_feedback_v1')
            assert final['stop_reason'] == 'feedback_round_complete', final
        replay = controller.run_controller(folder, profile='shared_scorer_feedback_v1')
        assert replay['budget'] == final['budget'] and len(calls) == 7
    return folder, final


def test_feedback_real_training_preserves_first_round_and_only_changes_step_size(completed_feedback):
    folder, state = completed_feedback
    from src.ai_workflow.research_tasks import read_json
    before = read_json(folder / 'candidate_run/results.json')
    after = read_json(folder / 'candidate_step_run/results.json')
    assert before['config']['learning_rate'] == .01 and after['config']['learning_rate'] == .1
    assert {k:v for k,v in before['config'].items() if k != 'learning_rate'} == {
        k:v for k,v in after['config'].items() if k != 'learning_rate'}
    assert len(state['tasks']) == 7 and state['research_status'] == 'not_achieved'
    assert state['budget']['provider_calls'] == 0
    assert after['feedback']['only_changed_factor'] == 'learning_rate'
    assert after['feedback']['same_initial_parameters'] is True
    assert after['feedback']['total_training_steps'] == 3072
    for a,b in zip(before['training_runs'], after['training_runs']):
        assert a['checkpoints']['initial']['state_sha256'] == b['checkpoints']['initial']['state_sha256']
    for mode, decision in after['decisions'].items():
        if decision['selected_method'] != 'none':
            assert decision['mean_validation_tardiness']['shared_scorer_v1'] < before['decisions'][mode]['mean_validation_tardiness']['shared_scorer_v1']


@pytest.mark.parametrize('target', ['diagnosis', 'hypothesis', 'trial_config', 'trial_checkpoint', 'receipt'])
def test_feedback_tampering_denies_terminal_resume(completed_feedback, tmp_path, target):
    import shutil
    from src.ai_workflow.research_controller import run_controller
    folder = tmp_path / 'tampered'
    shutil.copytree(completed_feedback[0], folder)
    paths = {'diagnosis': 'candidate_diagnosis/report.json', 'hypothesis': 'candidate_diagnosis/hypothesis.json',
        'trial_config': 'candidate_step_run/config.json', 'receipt': 'task_06.json'}
    path = folder / paths[target] if target != 'trial_checkpoint' else next((folder/'candidate_step_run/checkpoints').rglob('*.npz'))
    path.write_bytes(b'{}')
    with pytest.raises((ValueError, KeyError)):
        run_controller(folder, profile='shared_scorer_feedback_v1')


def test_rehashed_fake_diagnosis_cannot_authorize_another_hypothesis(completed_feedback, tmp_path):
    import shutil
    from src.ai_workflow.research_tasks import encoded, read_json, sha
    folder = tmp_path / 'fake-diagnosis'
    shutil.copytree(completed_feedback[0], folder)
    report = read_json(folder/'task_06.json')
    report['hypothesis']['learning_rate'] = .2
    report['hypothesis_sha256'] = sha(encoded(report['hypothesis']))
    (folder/'candidate_diagnosis/hypothesis.json').write_bytes(encoded(report['hypothesis']))
    (folder/'candidate_diagnosis/report.json').write_bytes(encoded({k:v for k,v in report.items() if k != 'artifacts'}))
    report['artifacts'] = {p: sha((folder/p).read_bytes()) for p in report['artifacts']}
    with pytest.raises(ValueError, match='verified replay'):
        api().verify_diagnosis(report, folder)


def test_rehashed_trial_configuration_cannot_change_the_registered_experiment(completed_feedback, tmp_path):
    import shutil
    from src.ai_workflow.research_tasks import encoded, read_json, sha
    from src.ai_workflow.controlled_candidate import verify_candidate_result
    folder = tmp_path / 'fake-config'
    shutil.copytree(completed_feedback[0], folder)
    prefix = folder/'candidate_step_run'
    report = read_json(folder/'task_07.json')
    report['config']['learning_rate'] = .2
    (prefix/'config.json').write_bytes(encoded(report['config']))
    (prefix/'results.json').write_bytes(encoded({k:v for k,v in report.items() if k != 'artifacts'}))
    manifest = read_json(prefix/'manifest.json')
    manifest['artifacts'] = {p:sha((folder/p).read_bytes()) for p in manifest['artifacts']}
    (prefix/'manifest.json').write_bytes(encoded(manifest))
    report['artifacts'] = {p:sha((folder/p).read_bytes()) for p in report['artifacts']}
    with pytest.raises(ValueError, match='registered configuration'):
        verify_candidate_result('compare_larger_step', report, folder)


def test_diagnosis_never_decodes_held_out_data(tmp_path, monkeypatch):
    import shutil
    from src.ai_workflow.research_tasks import encoded, sha
    from src.ai_workflow import candidate_replay
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    module = api()
    raw = json.loads((REFERENCE/'results.json').read_bytes())
    raw['splits']['probe'] = {'NEVER_DECODE_PROBE': True}
    raw['splits']['final_test'] = {'NEVER_DECODE_PROBE': True}
    reference = tmp_path/'reference'
    reference.mkdir()
    (reference/'results.json').write_bytes(encoded(raw))
    manifest = json.loads((REFERENCE/'manifest.json').read_bytes())
    manifest['artifacts']['results.json'] = sha((reference/'results.json').read_bytes())
    (reference/'manifest.json').write_bytes(encoded(manifest))
    batch = tmp_path/'batch'
    shutil.copytree(ARCHIVE, batch)
    inputs = json.loads((batch/'candidate_run/inputs.json').read_bytes())
    inputs['reference_manifest_sha256'] = sha((reference/'manifest.json').read_bytes())
    inputs['reference_results_sha256'] = sha((reference/'results.json').read_bytes())
    (batch/'candidate_run/inputs.json').write_bytes(encoded(inputs))
    original = module._decode
    def guarded(value):
        assert 'NEVER_DECODE_PROBE' not in value
        return original(value)
    monkeypatch.setattr(module, '_decode', guarded)
    monkeypatch.setattr(candidate_replay, '_decode', guarded)
    report = module.analyse_comparison(batch, reference,
        json.loads((ARCHIVE/'candidate_run/results.json').read_bytes()), SharedScorer)
    assert report['probe_evaluated'] is False and report['final_test_evaluated'] is False


def test_unregistered_trial_refuses_before_creating_outputs(tmp_path):
    from src.ai_workflow.candidate_comparison import run_comparison
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    with pytest.raises(ValueError, match='Unregistered'):
        run_comparison(tmp_path, REFERENCE, SharedScorer, trial='free_search')
    assert list(tmp_path.iterdir()) == []


def test_rehashed_zero_data_hash_does_not_replace_real_split_identity(completed_feedback, tmp_path):
    import shutil
    from src.ai_workflow.research_tasks import encoded, read_json, sha
    from src.ai_workflow.controlled_candidate import verify_candidate_result
    folder = tmp_path/'fake-data'
    shutil.copytree(completed_feedback[0], folder)
    prefix = folder/'candidate_step_run'
    report = read_json(folder/'task_07.json')
    inputs = read_json(prefix/'inputs.json')
    inputs['data_sha256'] = '0'*64
    (prefix/'inputs.json').write_bytes(encoded(inputs))
    manifest = read_json(prefix/'manifest.json')
    manifest['artifacts'] = {p:sha((folder/p).read_bytes()) for p in manifest['artifacts']}
    (prefix/'manifest.json').write_bytes(encoded(manifest))
    report['artifacts'] = {p:sha((folder/p).read_bytes()) for p in report['artifacts']}
    with pytest.raises(ValueError, match='data identity'):
        verify_candidate_result('compare_larger_step', report, folder)


def test_parent_result_validation_obeys_remaining_budget(completed_feedback):
    from src.ai_workflow.research_tasks import validate_task_result, read_json
    folder, _ = completed_feedback
    def expired(): raise TimeoutError('remaining parent budget')
    with pytest.raises(TimeoutError, match='remaining parent'):
        validate_task_result('compare_larger_step', read_json(folder/'task_07.json'),
                             batch_dir=folder, check_budget=expired)


def test_rehashed_feasible_control_substitution_is_rejected(completed_feedback, tmp_path):
    import shutil
    from copy import deepcopy
    from src.ai_workflow.research_tasks import encoded, read_json, sha
    from src.ai_workflow.candidate_comparison import _decisions
    from src.ai_workflow.controlled_candidate import verify_candidate_result
    folder = tmp_path/'fake-control'
    shutil.copytree(completed_feedback[0], folder)
    report = read_json(folder/'task_05.json')
    for row, candidate in zip(report['control_rows'], report['candidate_rows']):
        for key in ('payload', 'actions', 'rewards', 'plan_sha256'):
            row[key] = deepcopy(candidate[key])
        row['saved_plan_sha256'] = row['plan_sha256']
    report['validation_rows'] = report['candidate_rows'] + report['control_rows']
    report['decisions'] = _decisions(report['validation_rows'], complete=True)
    prefix = folder/'candidate_run'
    (prefix/'results.json').write_bytes(encoded({k:v for k,v in report.items() if k != 'artifacts'}))
    manifest = read_json(prefix/'manifest.json')
    manifest['artifacts'] = {p:sha((folder/p).read_bytes()) for p in manifest['artifacts']}
    (prefix/'manifest.json').write_bytes(encoded(manifest))
    report['artifacts'] = {p:sha((folder/p).read_bytes()) for p in report['artifacts']}
    with pytest.raises(ValueError, match='frozen none control'):
        verify_candidate_result('compare_shared_scorer', report, folder)


def test_interrupted_second_trial_is_not_restarted(completed_feedback, tmp_path, monkeypatch):
    import shutil
    from src.ai_workflow import research_controller as controller
    from src.ai_workflow.research_tasks import read_json, encoded
    folder = tmp_path/'interrupted'
    shutil.copytree(completed_feedback[0], folder)
    state = read_json(folder/'state.json')
    state.update(status='RUNNING', stop_reason=None, next_task=None)
    state['tasks'][-1]['status'] = 'RUNNING'
    (folder/'state.json').write_bytes(encoded(state))
    def forbidden(*a, **k): pytest.fail('Interrupted trial must not be resubmitted')
    monkeypatch.setattr(controller, 'supervised_json_process', forbidden)
    result = controller.run_controller(folder, profile='shared_scorer_feedback_v1')
    assert result['stop_reason'] == 'interrupted_task'
