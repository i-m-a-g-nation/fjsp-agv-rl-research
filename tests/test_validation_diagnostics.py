"""Small native archives exercise diagnostics without evaluating pilot probes."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.neural_policy import MaskedMLP


ROOT = Path(__file__).resolve().parents[1]
SOURCES = tuple('src/graduation/' + name + '.py' for name in (
    'data', 'result', 'metrics', 'feasibility', '_production', 'rl_environment',
    'rules', 'solver', 'state_encoding', 'neural_policy', 'policy_training',
)) + ('src/scheduling/encoding.py', 'src/scheduling/feasibility.py', 'src/data/instance.py',
      'experiments/exp_025_neural_policy_pilot.py')


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _state_hash(state):
    digest = hashlib.sha256()
    for name in sorted(state):
        value = state[name]
        digest.update(_encoded({'name': name, 'dtype': value.dtype.str, 'shape': value.shape}))
        digest.update(value.tobytes(order='C'))
    return digest.hexdigest()


def _write(path, value):
    path.write_bytes(_encoded(value))


def _refresh_manifest(archive):
    path = archive / 'manifest.json'
    manifest = json.loads(path.read_bytes())
    manifest['artifacts'] = {p.relative_to(archive).as_posix(): _sha(p.read_bytes())
                             for p in archive.rglob('*') if p.is_file() and p != path}
    _write(path, manifest)


def _archive(tmp_path):
    archive = tmp_path / 'native'
    archive.mkdir()
    data = ParallelMaintenanceInstance((ProductionTask(0, 3, 3), ProductionTask(1, 1, 1)),
        1, (MaintenanceRequirement(0, 2, 0, 6, 0),))
    train = ParallelMaintenanceInstance((ProductionTask(0, 3, 0), ProductionTask(1, 1, 0)),
        1, data.maintenance)

    def row(data, seed):
        raw = asdict(data)
        identity = _sha(json.dumps([[x.processing_time, x.due_date] for x in data.tasks],
                                   separators=(',', ':')).encode())
        return {'seed': seed, 'base_instance_identity': identity, 'input': raw,
                'input_sha256': _sha(_encoded(raw))}

    source_hashes = {p: _sha((ROOT / p).read_bytes()) for p in SOURCES}
    state = MaskedMLP(seed=17).state_dict()
    for value in state.values():
        value[:] = 0.
    state['b2'][96], state['b2'][0] = 3., 2.
    saved = archive / 'selected.npz'
    np.savez_compressed(saved, **state)
    metadata = {'path': 'selected.npz', 'sha256': _sha(saved.read_bytes()),
        'state_sha256': _state_hash(state), 'episode': 0, 'trained': False,
        'source_hashes': source_hashes, 'config_sha256': 'a' * 64, 'data_sha256': 'b' * 64}
    _write(saved.with_suffix('.json'), metadata)
    trainrow, validationrow = row(train, 1001), row(data, 2001)
    run = {'mode': 'fixed', 'seed': 17, 'status': 'COMPLETED', 'selected_episode': 0,
        'episodes_completed': 1, 'training_steps': 3, 'checkpoints': {'selected': metadata},
        'logs': [{'episode': 1, 'training_index': 0,
            'instance_identity': trainrow['base_instance_identity'], 'actions': [96, 0, 4],
            'rewards': [0., -.05, -.06], 'total_reward': -.11, 'total_tardiness': 11,
            'update': {'gradient_norm': 2., 'applied_gradient_norm': 1.,
                       'changed': True, 'samples': 3}}],
        'validation_history': [{'episode': 0, 'validation_mean_tardiness': 7.,
            'validation_rows': [{'validation_index': 0, 'actions': [96, 0, 4],
                'instance_identity': validationrow['base_instance_identity'],
                'rewards': [0., -.02, -.05], 'total_reward': -.07,
                'total_tardiness': 7}]}]}
    _write(archive / 'results.json', {'training_runs': [run],
        'splits': {'training': [trainrow], 'validation': [validationrow],
                   'probe': {'FORBIDDEN_PROBE_SENTINEL': 'never construct'}},
        'probe_rows': {'FORBIDDEN_PROBE_SENTINEL': 'never decode'},
        'cp_rows': {'FORBIDDEN_PROBE_SENTINEL': 'never decode'}})
    _write(archive / 'manifest.json', {'artifacts': {}, 'source_hashes': source_hashes,
        'config_sha256': 'a' * 64, 'data_sha256': 'b' * 64})
    _refresh_manifest(archive)
    return archive


def _api():
    from src.graduation.validation_diagnostics import diagnose_validation
    return diagnose_validation


def test_replays_selected_plans_and_literal_prefix_counterfactuals_without_writing(tmp_path):
    archive = _archive(tmp_path)
    before = {p: p.read_bytes() for p in archive.rglob('*') if p.is_file()}
    report = _api()(archive)
    assert report['version'] == 1 and report['kind'] == 'validation_only_policy_diagnosis'
    assert report['probe_evaluated'] is report['cp_evaluated'] is False
    assert {p: p.read_bytes() for p in archive.rglob('*') if p.is_file()} == before
    run = report['runs'][0]
    assert run['selected_episode'] == 0
    val = run['validation'][0]
    assert val['greedy_actions'] == [96, 0, 4]
    assert val['EDD_actions'] == [96, 4, 0]
    assert (val['greedy_total_tardiness'], val['EDD_total_tardiness']) == (7, 5)
    assert [x['total_tardiness'] for x in val['prefix_EDD_continuations']] == [5, 5, 7, 7]
    assert all(x['G1_accepted'] for x in val['prefix_EDD_continuations'])
    assert run['summary']['action_agreement'] == 2
    assert run['summary']['divergence_counts'] == {'same': 2, 'production_order': 1}
    assert val['states'][1]['machine_tails'] == [2]
    assert val['states'][1]['probability_EDD'] == pytest.approx(.11920292202211755)
    assert val['states'][1]['probability_uniform_EDD'] == .5
    assert report['aggregate']['selected_greedy_G1_accepted'] == 1
    assert report['aggregate']['prefix_continuation_G1_accepted'] == 4
    stats = run['training_diagnostics']
    assert (stats['clip_count'], stats['changed_updates']) == (1, 1)
    assert (stats['reward_to_go_negative'], stats['reward_to_go_zero'],
            stats['reward_to_go_positive']) == (3, 0, 0)


def test_does_not_decode_any_probe_or_cp_subtree(tmp_path, monkeypatch):
    archive = _archive(tmp_path)
    real_loads = json.loads

    def loads(raw, *args, **kwargs):
        if 'FORBIDDEN_PROBE_SENTINEL' in (raw.decode() if isinstance(raw, bytes) else raw):
            raise AssertionError('A forbidden subtree was decoded')
        return real_loads(raw, *args, **kwargs)

    monkeypatch.setattr(json, 'loads', loads)
    assert _api()(archive)['probe_evaluated'] is False


@pytest.mark.parametrize('fault', ['tampered_file', 'missing_file', 'missing_artifact',
                                  'checkpoint_hash', 'state_hash', 'source_hash', 'omitted_actor'])
def test_rejects_incomplete_or_tampered_native_evidence(tmp_path, fault):
    archive = _archive(tmp_path)
    if fault == 'tampered_file':
        with (archive / 'results.json').open('ab') as handle:
            handle.write(b' ')
    elif fault == 'missing_file':
        (archive / 'selected.npz').unlink()
    elif fault == 'missing_artifact':
        manifest = json.loads((archive / 'manifest.json').read_bytes())
        del manifest['artifacts']['selected.npz']
        _write(archive / 'manifest.json', manifest)
    else:
        results = json.loads((archive / 'results.json').read_bytes())
        metadata = results['training_runs'][0]['checkpoints']['selected']
        if fault == 'checkpoint_hash':
            metadata['sha256'] = '0' * 64
        elif fault == 'state_hash':
            metadata['state_sha256'] = '0' * 64
        elif fault == 'source_hash':
            metadata['source_hashes']['src/graduation/neural_policy.py'] = '0' * 64
        else:
            del metadata['source_hashes']['src/graduation/neural_policy.py']
        _write(archive / 'selected.json', metadata)
        _write(archive / 'results.json', results)
        _refresh_manifest(archive)
    with pytest.raises((ValueError, FileNotFoundError), match='artifact|hash|source|checkpoint|selected|actor'):
        _api()(archive)


@pytest.mark.parametrize('path', ['../outside.npz', '/outside.npz', 'C:/outside.npz',
                                 'folder/../../outside.npz', 'folder\\outside.npz'])
def test_rejects_archive_path_escape_before_loading(tmp_path, path):
    archive = _archive(tmp_path)
    manifest = json.loads((archive / 'manifest.json').read_bytes())
    manifest['artifacts'][path] = '0' * 64
    _write(archive / 'manifest.json', manifest)
    with pytest.raises(ValueError, match='path|archive|relative'):
        _api()(archive)


def test_budget_interrupt_propagates_without_mutating_archive(tmp_path):
    archive = _archive(tmp_path)
    calls = 0

    def budget():
        nonlocal calls
        calls += 1
        if calls == 8:
            raise TimeoutError('diagnostic deadline')

    with pytest.raises(TimeoutError, match='diagnostic deadline'):
        _api()(archive, check_budget=budget)
    assert calls == 8


def test_rejects_bad_budget_before_reading(tmp_path):
    with pytest.raises(ValueError, match='budget|callable'):
        _api()(tmp_path / 'absent', check_budget=False)


@pytest.mark.parametrize('field,value', [('instance_identity', '0' * 64),
                                       ('rewards', [0., 0., 0.]), ('total_reward', 0.)])
def test_rejects_saved_validation_identity_or_reward_disagreement(tmp_path, field, value):
    archive = _archive(tmp_path)
    result = json.loads((archive / 'results.json').read_bytes())
    result['training_runs'][0]['validation_history'][0]['validation_rows'][0][field] = value
    _write(archive / 'results.json', result)
    _refresh_manifest(archive)
    with pytest.raises(ValueError, match='validation|reward|identity'):
        _api()(archive)


def test_rejects_gradient_clipping_diagnostics_that_disagree_with_original_actor(tmp_path):
    archive = _archive(tmp_path)
    result = json.loads((archive / 'results.json').read_bytes())
    result['training_runs'][0]['logs'][0]['update']['applied_gradient_norm'] = .1
    _write(archive / 'results.json', result)
    _refresh_manifest(archive)
    with pytest.raises(ValueError, match='gradient'):
        _api()(archive)


def test_budget_is_checked_between_real_replay_steps(tmp_path, monkeypatch):
    from src.graduation import validation_diagnostics as diagnostics
    archive = _archive(tmp_path)
    real_step = diagnostics.ParallelMaintenanceEnv.step
    expired = False

    def step(self, action):
        nonlocal expired
        value = real_step(self, action)
        expired = True
        return value

    def budget():
        if expired:
            raise TimeoutError('expired after first real step')

    monkeypatch.setattr(diagnostics.ParallelMaintenanceEnv, 'step', step)
    with pytest.raises(TimeoutError, match='first real step'):
        diagnostics.diagnose_validation(archive, check_budget=budget)


def test_internal_deadline_applies_without_external_callback(tmp_path, monkeypatch):
    from src.graduation import validation_diagnostics as diagnostics
    archive = _archive(tmp_path)
    clock = [0.]
    real_step = diagnostics.ParallelMaintenanceEnv.step

    def step(self, action):
        value = real_step(self, action)
        clock[0] = 120.
        return value

    monkeypatch.setattr(diagnostics.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(diagnostics.ParallelMaintenanceEnv, 'step', step)
    with pytest.raises(TimeoutError, match='120|budget'):
        diagnostics.diagnose_validation(archive)


def test_historical_trainer_hash_is_excluded_from_current_inference_checks(tmp_path):
    archive = _archive(tmp_path)
    result = json.loads((archive / 'results.json').read_bytes())
    manifest = json.loads((archive / 'manifest.json').read_bytes())
    metadata = result['training_runs'][0]['checkpoints']['selected']
    metadata['source_hashes']['src/graduation/policy_training.py'] = '0' * 64
    manifest['source_hashes']['src/graduation/policy_training.py'] = '0' * 64
    _write(archive / 'selected.json', metadata)
    _write(archive / 'results.json', result)
    _write(archive / 'manifest.json', manifest)
    _refresh_manifest(archive)
    report = _api()(archive)
    assert report['hash_checks']['historical_trainer_source_sha256'] == '0' * 64
    assert report['aggregate']['selected_greedy_G1_accepted'] == 1


def test_unsafe_object_npz_is_rejected_even_when_outer_hashes_match(tmp_path):
    archive = _archive(tmp_path)
    result = json.loads((archive / 'results.json').read_bytes())
    path = archive / 'selected.npz'
    np.savez(path, w1=np.asarray([{'unsafe': 'object'}], dtype=object))
    metadata = result['training_runs'][0]['checkpoints']['selected']
    metadata['sha256'] = _sha(path.read_bytes())
    _write(archive / 'selected.json', metadata)
    _write(archive / 'results.json', result)
    _refresh_manifest(archive)
    with pytest.raises(ValueError, match='Object|pickle'):
        _api()(archive)


@pytest.mark.parametrize('fault', ['G1', 'TT'])
def test_independent_checker_and_metric_can_refuse_a_replayed_plan(tmp_path, monkeypatch, fault):
    from src.graduation import validation_diagnostics as diagnostics
    archive = _archive(tmp_path)
    if fault == 'G1':
        monkeypatch.setattr(diagnostics, 'check_parallel_maintenance_feasibility',
                            lambda *a, **k: (False, ['independent refusal']))
    else:
        monkeypatch.setattr(diagnostics, 'calculate_total_tardiness', lambda *a: 999)
    with pytest.raises(ValueError, match='G1|tardiness'):
        diagnostics.diagnose_validation(archive)
