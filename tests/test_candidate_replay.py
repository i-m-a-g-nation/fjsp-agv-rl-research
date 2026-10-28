"""Declared data and optimizer steps must be derivable from frozen evidence."""
from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'experiments/results/exp_027_controlled_candidate_v1'
REFERENCE = ROOT/'experiments/results/exp_026_validation_iteration_v1'


def api():
    return importlib.import_module('src.ai_workflow.candidate_replay')


@pytest.mark.parametrize('native_sequences', [False, True])
def test_original_saved_training_is_numerically_reproducible(native_sequences):
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    report = json.loads((ARCHIVE/'candidate_run/results.json').read_bytes())
    if native_sequences:
        for run in report['training_runs']:
            for log in run['logs']:
                log['actions'] = tuple(log['actions'])
                log['rewards'] = tuple(log['rewards'])
    api()._VERIFIED.clear()  # Each representation must independently pass replay.
    api().verify_training_replay(ARCHIVE, REFERENCE, report, SharedScorer)


@pytest.mark.parametrize('damage', ['zero_gradient', 'false_rate', 'changed_seed', 'changed_action'])
def test_self_consistent_labels_cannot_replace_actual_updates(damage):
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    report = json.loads((ARCHIVE/'candidate_run/results.json').read_bytes())
    if damage == 'zero_gradient':
        for run in report['training_runs']:
            for log in run['logs']:
                log['update'].update(gradient_norm=0., applied_gradient_norm=0., changed=True)
    if damage == 'false_rate': report['config']['learning_rate'] = .1
    if damage == 'changed_seed': report['training_runs'][0]['logs'][0]['seed'] += 1
    if damage == 'changed_action': report['training_runs'][0]['logs'][0]['actions'][0] = 99
    with pytest.raises(ValueError, match='Replay|replay'):
        api().verify_training_replay(ARCHIVE, REFERENCE, report, SharedScorer)


def test_recomputed_split_identity_is_bound_to_real_reference_bytes():
    _, _, inputs = api().verified_splits(REFERENCE)
    manifest = json.loads((REFERENCE/'manifest.json').read_bytes())
    assert inputs['data_sha256'] == manifest['data_sha256']
    assert len(inputs['training_base_identities']) == 8 and len(inputs['validation_base_identities']) == 4
    assert not set(inputs['training_base_identities']) & set(inputs['validation_base_identities'])


@pytest.mark.parametrize('damage', ['broadcast_shape', 'integer_dtype'])
def test_parameter_comparison_rejects_schema_changes(damage):
    import numpy as np
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    expected = SharedScorer(seed=17, hidden_size=16).state_dict()
    actual = {k:v.copy() for k,v in expected.items()}
    if damage == 'broadcast_shape': actual['w1'] = actual['w1'][None, :, :]
    if damage == 'integer_dtype': actual['b1'] = actual['b1'].astype(np.int64)
    assert not api()._same_state(actual, expected)


def test_numeric_verifier_observes_remaining_budget_even_on_cache_hit():
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    report = json.loads((ARCHIVE/'candidate_run/results.json').read_bytes())
    def expired(): raise TimeoutError('remaining cumulative budget')
    with pytest.raises(TimeoutError, match='remaining'):
        api().verify_training_replay(ARCHIVE, REFERENCE, report, SharedScorer, check_budget=expired)


@pytest.mark.parametrize('damage', ['selected_plan', 'interval_mean', 'interval_plan',
                                  'reference_control', 'reference_rule', 'reference_cp'])
def test_validation_claims_must_come_from_saved_parameters(damage):
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    report = json.loads((ARCHIVE/'candidate_run/results.json').read_bytes())
    if damage == 'selected_plan':
        # A feasible control plan must not be attributed to the candidate actor.
        report['candidate_rows'][0]['payload'] = deepcopy(report['control_rows'][0]['payload'])
        report['candidate_rows'][0]['actions'] = deepcopy(report['control_rows'][0]['actions'])
    if damage == 'interval_mean':
        report['training_runs'][0]['validation_history'][1]['validation_mean_tardiness'] = 0.
    if damage == 'interval_plan':
        report['training_runs'][0]['validation_history'][1]['validation_rows'][0]['actions'][0] = 99
    if damage == 'reference_control':
        report['control_rows'][0]['payload'] = deepcopy(report['candidate_rows'][0]['payload'])
        report['control_rows'][0]['actions'] = deepcopy(report['candidate_rows'][0]['actions'])
    if damage == 'reference_rule': report['rule_rows'][0]['payload']['total_tardiness'] += 1
    if damage == 'reference_cp': report['cp_rows'][0]['solver_objective_value'] += 1
    api()._VERIFIED.clear()
    with pytest.raises(ValueError, match='Replay|replay'):
        api().verify_training_replay(ARCHIVE, REFERENCE, report, SharedScorer)


@pytest.mark.parametrize('seconds', [120.1, 600])
def test_feedback_cannot_expand_its_declared_active_budget(tmp_path, seconds):
    from src.ai_workflow.research_controller import run_controller
    folder = tmp_path/'over-budget'
    with pytest.raises(ValueError, match='120'):
        run_controller(folder, track='innovation', profile='shared_scorer_feedback_v1', max_active_seconds=seconds)
    assert not folder.exists()
