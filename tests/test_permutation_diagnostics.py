"""Synthetic frozen archives exercise relabeling without training or probe use."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.neural_policy import MaskedMLP
from src.graduation.rl_environment import ParallelMaintenanceEnv
from src.graduation.state_encoding import encode_construction_observation

ROOT = Path(__file__).resolve().parents[1]
SOURCES = tuple('src/graduation/' + name + '.py' for name in (
    'data', 'result', 'metrics', 'feasibility', '_production', 'rl_environment',
    'rules', 'solver', 'state_encoding', 'neural_policy', 'policy_training',
    'return_baseline', 'validation_diagnostics')) + (
    'src/scheduling/encoding.py', 'src/scheduling/feasibility.py', 'src/data/instance.py',
    'experiments/exp_025_neural_policy_pilot.py', 'experiments/exp_026_validation_iteration.py')


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write(path, value):
    path.write_bytes(encoded(value))


def refresh(archive):
    path = archive / 'manifest.json'
    manifest = json.loads(path.read_bytes())
    manifest['artifacts'] = {p.relative_to(archive).as_posix(): sha(p.read_bytes())
                             for p in archive.rglob('*') if p.is_file() and p != path}
    write(path, manifest)


def plan(data, mode, actor):
    env, actions, rewards = ParallelMaintenanceEnv(data, mode=mode), [], []
    for _ in range(len(data.tasks) + data.num_machines):
        probabilities = actor.probabilities(encode_construction_observation(env.observe()))
        action = int(np.argmax(probabilities))
        actions.append(action)
        rewards.append(env.step(action).reward)
    result = env.get_result()
    return actions, rewards, {'records': [asdict(x) for x in result.records],
        'maintenance_records': [asdict(x) for x in result.maintenance_records],
        'makespan': result.makespan, 'total_tardiness': result.total_tardiness}


@pytest.fixture
def archive(tmp_path):
    root = tmp_path / 'frozen'
    root.mkdir()
    source_hashes = {name: sha((ROOT / name).read_bytes()) for name in SOURCES}
    state = MaskedMLP(seed=17).state_dict()
    for value in state.values():
        value[:] = 0.
    state['b2'][0], state['b2'][4], state['b2'][96], state['b2'][97] = 3., 2., 1., .5
    actor = MaskedMLP.from_state(state)
    validation, data_rows = [], []
    for index in range(4):
        data = ParallelMaintenanceInstance((ProductionTask(0, 3, index), ProductionTask(1, 1, 4)),
            2, (MaintenanceRequirement(0, 2, 0, 8, 0), MaintenanceRequirement(1, 1, 1, 9, 1)))
        raw = asdict(data)
        validation.append({'seed': 2000 + index, 'input': raw, 'input_sha256': sha(encoded(raw)),
            'base_instance_identity': sha(json.dumps([[t.processing_time, t.due_date] for t in data.tasks],
                                                    separators=(',', ':')).encode())})
        data_rows.append(data)
    runs, rows = [], []
    for mode in ('fixed', 'joint'):
        for seed in (17, 29):
            relative = f'checkpoints/none-{mode}-seed{seed}/selected.npz'
            path = root / relative
            path.parent.mkdir(parents=True)
            np.savez_compressed(path, **state)
            digest = hashlib.sha256()
            for name in sorted(state):
                value = state[name]
                digest.update(encoded({'name': name, 'dtype': value.dtype.str, 'shape': value.shape}))
                digest.update(value.tobytes(order='C'))
            metadata = {'path': relative, 'sha256': sha(path.read_bytes()), 'state_sha256': digest.hexdigest(),
                'episode': 0, 'trained': False, 'source_hashes': source_hashes,
                'config_sha256': 'a' * 64, 'data_sha256': 'b' * 64}
            write(path.with_suffix('.json'), metadata)
            runs.append({'method': 'none', 'mode': mode, 'seed': seed, 'status': 'COMPLETED',
                'selected_episode': 0, 'episodes_completed': 64, 'checkpoints': {'selected': metadata,
                    'final': {'FORBIDDEN_VALUE': 'unused checkpoint'}},
                'logs': {'FORBIDDEN_VALUE': 'training log'},
                'validation_history': {'FORBIDDEN_VALUE': 'training selection history'}})
            for index, data in enumerate(data_rows):
                actions, rewards, payload = plan(data, mode, actor)
                rows.append({'method': 'none', 'mode': mode, 'seed': seed, 'validation_index': index,
                    'instance_identity': validation[index]['base_instance_identity'], 'actions': actions,
                    'transitions': [{'reward': reward} for reward in rewards], 'payload': payload,
                    'validation_status': 'PASS', 'schedule_accepted': True})
    write(root / 'results.json', {'training_runs': runs, 'validation_rows': rows,
        'splits': {'validation': validation, 'training': {'FORBIDDEN_VALUE': 'training inputs'},
                   'probe': {'FORBIDDEN_VALUE': 'probe'}}, 'final_test': {'FORBIDDEN_VALUE': 'test'}})
    write(root / 'manifest.json', {'artifacts': {}, 'source_hashes': source_hashes,
        'config_sha256': 'a' * 64, 'data_sha256': 'b' * 64, 'status': 'COMPLETED',
        'purpose': 'validation_only_return_baseline_iteration',
        'decisions': {mode: {'selected_method': 'none', 'status': 'DECIDED'} for mode in ('fixed', 'joint')}})
    refresh(root)
    return root


def diagnose(archive, **kwargs):
    from src.graduation.permutation_diagnostics import diagnose_permutations
    return diagnose_permutations(archive, **kwargs)


def rebind_actor(archive, state):
    actor = MaskedMLP.from_state(state)
    result = json.loads((archive / 'results.json').read_bytes())
    digest = hashlib.sha256()
    for name in sorted(state):
        value = state[name]
        digest.update(encoded({'name': name, 'dtype': value.dtype.str, 'shape': value.shape}))
        digest.update(value.tobytes(order='C'))
    for run in result['training_runs']:
        meta = run['checkpoints']['selected']
        path = archive / meta['path']
        np.savez_compressed(path, **state)
        meta.update(sha256=sha(path.read_bytes()), state_sha256=digest.hexdigest())
        write(path.with_suffix('.json'), meta)
    for row in result['validation_rows']:
        raw = result['splits']['validation'][row['validation_index']]['input']
        data = ParallelMaintenanceInstance(tuple(ProductionTask(**t) for t in raw['tasks']), raw['num_machines'],
            tuple(MaintenanceRequirement(**m) for m in raw['maintenance']))
        actions, rewards, payload = plan(data, row['mode'], actor)
        row.update(actions=actions, transitions=[{'reward': reward} for reward in rewards], payload=payload)
    write(archive / 'results.json', result)
    refresh(archive)


def test_complete_same_state_replays_and_greedy_plans_are_independently_checkable(archive):
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult
    from src.graduation.data import to_fjsp_instance
    from src.scheduling.encoding import ScheduleRecord

    before = {p: p.read_bytes() for p in archive.rglob('*') if p.is_file()}
    report = diagnose(archive)
    assert report['status'] == 'COMPLETED' and report['kind'] == 'validation_only_permutation_diagnosis'
    assert report['research_status'] == 'not_achieved'
    assert report['probe_evaluated'] is report['final_test_evaluated'] is False
    assert report['denominators'] == {'expected_original_cases': 16, 'original_cases': 16,
        'expected_permutation_cases': 64, 'permutation_cases': 64,
        'expected_state_comparisons': 256, 'state_comparisons': 256, 'G1_accepted_greedy_plans': 64,
        'G1_accepted_mapped_replay_plans': 64}
    assert report['sensitive_states'] > 0
    assert {p: p.read_bytes() for p in archive.rglob('*') if p.is_file()} == before
    for case in report['cases']:
        raw = case['input']
        data = ParallelMaintenanceInstance(tuple(ProductionTask(**t) for t in raw['tasks']), raw['num_machines'],
            tuple(MaintenanceRequirement(**m) for m in raw['maintenance']))
        payload = case['greedy']['payload']
        result = MaintenanceScheduleResult(instance=to_fjsp_instance(data), makespan=payload['makespan'],
            total_tardiness=payload['total_tardiness'], records=[ScheduleRecord(**r) for r in payload['records']],
            maintenance_records=[MaintenanceRecord(**r) for r in payload['maintenance_records']])
        assert check_parallel_maintenance_feasibility(result, data, mode=case['mode'])[0]
        assert len(result.maintenance_records) == 2
        assert sum(case['greedy']['rewards']) == pytest.approx(-result.total_tardiness / 100)
        assert sorted(case['action_map']) == list(range(100))
        assert all(state['same_physical_state'] and state['uniform_max_error'] == 0 for state in case['states'])
        if case['permutation'] == 'identity':
            assert case['max_probability_error'] == case['l1_probability_error'] == 0
            if case['mode'] == 'fixed':
                assert {record.machine_id for record in result.records} == {0}
        if case['permutation'] == 'jobs_reverse':
            assert case['action_map'][0] == 4 and case['action_map'][4] == 0
            assert case['mapped_replay']['actions'] != case['greedy']['actions']
    json.dumps(report, allow_nan=False)


def test_feature_dependent_logits_use_permuted_normalized_task_features(archive):
    state = MaskedMLP(seed=17).state_dict()
    for value in state.values():
        value[:] = 0.
    state['w1'][0, 0], state['w2'][0, 96] = 1., 1.
    rebind_actor(archive, state)
    report = diagnose(archive)
    case = next(c for c in report['cases'] if (c['mode'], c['seed'], c['validation_index'], c['permutation']) ==
                ('fixed', 17, 0, 'jobs_reverse'))
    first = case['states'][0]
    original = np.exp(np.tanh(1.5)) / (np.exp(np.tanh(1.5)) + 2)
    transformed = np.exp(np.tanh(.5)) / (np.exp(np.tanh(.5)) + 2)
    assert first['probabilities'][96] == pytest.approx(original)
    assert first['mapped_probabilities'][96] == pytest.approx(transformed)
    assert first['max_probability_error'] == pytest.approx(original - transformed)
    assert first['original_features_sha256'] != first['permuted_features_sha256']


def test_uniform_actor_is_equivariant_despite_possible_greedy_tie_breaking(archive):
    state = MaskedMLP(seed=17).state_dict()
    for value in state.values():
        value[:] = 0.
    rebind_actor(archive, state)
    report = diagnose(archive)
    assert report['sensitive_states'] == 0
    assert report['aggregate']['uniform_sensitive_states'] == 0
    assert all(case['max_probability_error'] == 0 for case in report['cases'])


def test_skips_training_probe_final_and_nonselected_checkpoint_values(archive, monkeypatch):
    real = json.loads

    def guarded(raw, *args, **kwargs):
        assert 'FORBIDDEN_VALUE' not in (raw.decode() if isinstance(raw, bytes) else raw)
        return real(raw, *args, **kwargs)

    monkeypatch.setattr(json, 'loads', guarded)
    assert diagnose(archive)['denominators']['permutation_cases'] == 64


@pytest.mark.parametrize('fault', ['artifact', 'source', 'state', 'missing_case', 'duplicate_case',
                                  'bad_input', 'saved_plan', 'selected_method'])
def test_rejects_tampering_and_incomplete_denominators(archive, fault):
    result = json.loads((archive / 'results.json').read_bytes())
    manifest = json.loads((archive / 'manifest.json').read_bytes())
    if fault == 'artifact':
        with (archive / result['training_runs'][0]['checkpoints']['selected']['path']).open('ab') as handle:
            handle.write(b'changed')
    elif fault == 'source':
        manifest['source_hashes']['src/graduation/policy_training.py'] = '0' * 64
        write(archive / 'manifest.json', manifest)
    elif fault == 'selected_method':
        manifest['decisions']['fixed']['selected_method'] = 'running_mean'
        write(archive / 'manifest.json', manifest)
    else:
        if fault == 'state':
            meta = result['training_runs'][0]['checkpoints']['selected']
            meta['state_sha256'] = '0' * 64
            write((archive / meta['path']).with_suffix('.json'), meta)
        elif fault == 'missing_case':
            result['validation_rows'].pop()
        elif fault == 'duplicate_case':
            result['validation_rows'][-1] = result['validation_rows'][0]
        elif fault == 'bad_input':
            result['splits']['validation'][0]['input']['maintenance'][1]['window_end'] = 1
        else:
            result['validation_rows'][0]['payload']['records'][0]['end'] += 1
        write(archive / 'results.json', result)
        refresh(archive)
    with pytest.raises((ValueError, FileNotFoundError)):
        diagnose(archive)


def test_original_checker_rejection_is_fatal(archive, monkeypatch):
    from src.graduation import permutation_diagnostics as module
    monkeypatch.setattr(module, 'check_parallel_maintenance_feasibility', lambda *a, **k: (False, ['rejected']))
    with pytest.raises(ValueError, match='G1'):
        diagnose(archive)


def test_omitted_frozen_solver_source_cannot_evade_current_source_verification(archive):
    result = json.loads((archive / 'results.json').read_bytes())
    manifest = json.loads((archive / 'manifest.json').read_bytes())
    del manifest['source_hashes']['src/graduation/solver.py']
    for run in result['training_runs']:
        meta = run['checkpoints']['selected']
        meta['source_hashes'] = manifest['source_hashes']
        write((archive / meta['path']).with_suffix('.json'), meta)
    write(archive / 'results.json', result)
    write(archive / 'manifest.json', manifest)
    refresh(archive)
    with pytest.raises(ValueError, match='source'):
        diagnose(archive)


def test_budget_stop_propagates_without_writes(archive):
    def stop():
        raise TimeoutError('budget')
    with pytest.raises(TimeoutError, match='budget'):
        diagnose(archive, check_budget=stop)
