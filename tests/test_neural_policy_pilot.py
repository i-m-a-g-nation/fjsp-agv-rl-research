"""The pilot retains all denominators and reloads finite, safe checkpoints."""

from dataclasses import asdict
import hashlib
import json

import pytest


def test_generator_has_disjoint_reproducible_base_tasks_and_declared_windows():
    from experiments.exp_025_neural_policy_pilot import build_splits

    splits = build_splits()
    assert [len(splits[key]) for key in ('training', 'validation', 'probe')] == [8, 4, 4]
    assert splits == build_splits()
    identities = []
    for key, seeds in (('training', range(1001, 1009)), ('validation', range(2001, 2005)),
                       ('probe', range(3001, 3005))):
        for data, metadata, seed in zip(splits[key], splits['metadata'][key], seeds):
            assert metadata['seed'] == seed and metadata['input'] == asdict(data)
            assert len(data.tasks) == 4 and data.num_machines == 2
            work = sum(task.processing_time for task in data.tasks)
            assert all(1 <= task.processing_time <= 6 and 0 <= task.due_date <= work for task in data.tasks)
            identity = hashlib.sha256(json.dumps([[task.processing_time, task.due_date]
                for task in data.tasks], separators=(',', ':')).encode()).hexdigest()
            identities.append(identity)
            assert metadata['base_instance_identity'] == identity
            assert metadata['stream_version'] == 1 and len(metadata['stream_identity']) == 64
            for item in data.maintenance:
                assert 1 <= item.duration <= 3 and 0 <= item.window_start <= work // 3
                assert item.window_end == item.window_start + item.duration + max(1, work // 2)
                assert item.fixed_start == item.window_start + max(1, work // 2) // 2
    assert len(set(identities)) == 16
    assert splits['metadata']['purpose'] == 'engineering_probe_not_final_G3_test'


def _read(output):
    return json.loads((output / 'results.json').read_text(encoding='utf-8'))


def test_tiny_pilot_saves_all_96_plans_eight_references_and_reloaded_selected_predictions(tmp_path):
    from experiments import exp_025_neural_policy_pilot as module
    from src.graduation.policy_training import run_policy_episode

    output = tmp_path / 'run'
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    assert manifest['status'] == 'COMPLETED'
    assert manifest['expected_training_runs'] == manifest['completed_training_runs'] == 4
    assert manifest['expected_probe_rows'] == manifest['accepted_probe_rows'] == len(evidence['probe_rows']) == 96
    assert manifest['expected_cp_rows'] == manifest['accepted_cp_rows'] == len(evidence['cp_rows']) == 8
    assert manifest['training_steps'] == 24
    assert manifest['config']['parameter_count'] == 7668
    assert manifest['research_targets'] == {'paper_reproduction': 'not_achieved', 'graduation_research': 'not_achieved'}
    splits = module.build_splits()
    for row in evidence['probe_rows']:
        assert row['schedule_accepted'] and row['validation_status'] == 'PASS'
        assert len(row['actions']) == len(row['transitions']) == 6
        assert all(step['action_mask'][step['action']] for step in row['transitions'])
        assert row['payload']['total_reward'] == pytest.approx(-row['payload']['total_tardiness'] / 100)
        plan = {key: row['payload'][key] for key in
                ('total_tardiness', 'makespan', 'records', 'maintenance_records')}
        assert row['plan_sha256'] == hashlib.sha256(json.dumps(plan, sort_keys=True,
            ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()
        if row['method'] == 'selected':
            run = next(run for run in evidence['training_runs'] if run['mode'] == row['mode'] and run['seed'] == row['seed'])
            checkpoint = run['checkpoints']['selected']
            actor = module.load_checkpoint(output / checkpoint['path'], expected_sha256=checkpoint['sha256'])
            episode = run_policy_episode(splits['probe'][row['probe_index']], mode=row['mode'], actor=actor,
                seed=row['seed'], deterministic=True)
            assert list(episode.actions) == row['actions']
            assert episode.result.total_tardiness == row['payload']['total_tardiness']
    for run in evidence['training_runs']:
        assert run['episodes_completed'] == 1 and len(run['logs']) == 1
        assert run['checkpoints']['initial']['trained'] is False
        assert run['checkpoints']['selected']['trained'] == (run['selected_episode'] > 0)
        assert (output / run['progress_log']).is_file()
        assert len(run['validation_history']) == 2
    for row in evidence['cp_rows']:
        assert row['solver_status'] in ('OPTIMAL', 'FEASIBLE')
        assert row['optimum_certified'] == (row['solver_status'] == 'OPTIMAL')
        plan = {key: row['payload'][key] for key in
                ('total_tardiness', 'makespan', 'records', 'maintenance_records')}
        assert row['plan_sha256'] == hashlib.sha256(json.dumps(plan, sort_keys=True,
            ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()
    for relative, digest in manifest['artifacts'].items():
        assert hashlib.sha256((output / relative).read_bytes()).hexdigest() == digest
    assert manifest == json.loads((output / 'manifest.json').read_text())


def test_repeated_tiny_outcomes_ignore_paths_timings_and_refuse_overwrite(tmp_path):
    from experiments import exp_025_neural_policy_pilot as module

    first, second = tmp_path / 'one', tmp_path / 'two'
    a = module.run_experiment(first, episodes=1)
    b = module.run_experiment(second, episodes=1)
    assert a['status'] == b['status'] == 'COMPLETED'
    assert a['outcome_digest'] == b['outcome_digest']
    before = (first / 'manifest.json').read_bytes()
    with pytest.raises(FileExistsError):
        module.run_experiment(first, episodes=1)
    assert (first / 'manifest.json').read_bytes() == before


@pytest.mark.parametrize('cap', [0, -1, True, float('nan'), 121])
def test_invalid_budget_is_rejected_before_creating_output(tmp_path, cap):
    from experiments.exp_025_neural_policy_pilot import run_experiment
    output = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        run_experiment(output, episodes=1, max_active_seconds=cap)
    assert not output.exists()


def test_training_failure_preserves_episode_logs_checkpoints_and_all_denominators(tmp_path, monkeypatch):
    from experiments import exp_025_neural_policy_pilot as module
    from src.graduation import policy_training

    real = policy_training.train_policy

    def interrupted(*args, **kwargs):
        callback = kwargs['on_progress']

        def progress(event):
            callback(event)
            if event['kind'] == 'episode':
                raise RuntimeError('private controlled failure must not be copied')

        kwargs['on_progress'] = progress
        return real(*args, **kwargs)

    monkeypatch.setattr(policy_training, 'train_policy', interrupted)
    output = tmp_path / 'failed'
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    assert manifest['status'] == 'FAILED'
    assert manifest['completed_training_runs'] == 0
    assert manifest['accepted_probe_rows'] == 48
    assert len(evidence['probe_rows']) == 96 and len(evidence['cp_rows']) == 8
    assert all(run['status'] == 'FAILED' and len(run['logs']) == 1 for run in evidence['training_runs'])
    for run in evidence['training_runs']:
        assert run['error_type'] == 'RuntimeError'
        assert run['checkpoints']['initial']['trained'] is False
        assert (output / run['checkpoints']['initial']['path']).is_file()
        assert len((output / run['progress_log']).read_text().splitlines()) == 2
    assert b'private controlled failure' not in (output / 'results.json').read_bytes()


@pytest.mark.parametrize('status', ['OPTIMAL', 'FEASIBLE'])
def test_beating_optimal_is_rejected_but_beating_feasible_is_valid(tmp_path, monkeypatch, status):
    from experiments import exp_025_neural_policy_pilot as module
    from src.graduation.rules import run_maintenance_rule_episode

    def deliberately_poor_reference(data, *, mode, time_limit, num_workers, seed):
        assert 0 < time_limit <= 1 and num_workers == 1 and seed == 42
        candidates = [run_maintenance_rule_episode(data, mode=mode, rule='Random', seed=s).result for s in range(16)]
        result = max(candidates, key=lambda value: value.total_tardiness)
        result.solver_status = status
        result.solver_objective_value = float(result.total_tardiness)
        result.solver_objective_bound = float(result.total_tardiness) if status == 'OPTIMAL' else 0.
        result.solver_gap = 0. if status == 'OPTIMAL' else result.total_tardiness / max(1, result.total_tardiness)
        result.solver_wall_time = .001
        return result

    monkeypatch.setattr(module, 'solve_parallel_maintenance', deliberately_poor_reference)
    output = tmp_path / status
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    better = [row for row in evidence['probe_rows'] if row['cp_comparison']['tardiness_difference'] < 0]
    assert better
    assert all(row['solver_status'] == status for row in evidence['cp_rows'])
    if status == 'OPTIMAL':
        assert manifest['status'] == 'FAILED'
        assert all(not row['schedule_accepted'] and row['validation_status'] == 'FAIL' for row in better)
    else:
        assert manifest['status'] == 'COMPLETED'
        assert all(row['schedule_accepted'] for row in better)
        assert all(not row['optimum_certified'] for row in evidence['cp_rows'])


def test_timeout_after_last_call_cannot_complete_and_retains_all_rows(tmp_path, monkeypatch):
    from experiments import exp_025_neural_policy_pilot as module

    class Clock:
        now = 0.

        def monotonic(self):
            return self.now

    clock = Clock()
    monkeypatch.setattr(module.time, 'monotonic', clock.monotonic)
    real = module.run_maintenance_rule_episode
    target = module.build_splits()['probe'][3]

    def delayed(data, **kwargs):
        completed = real(data, **kwargs)
        if data == target and kwargs == {'mode': 'joint', 'rule': 'Random', 'seed': 29}:
            clock.now = 121.
        return completed

    monkeypatch.setattr(module, 'run_maintenance_rule_episode', delayed)
    output = tmp_path / 'late'
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    assert manifest['status'] == 'BUDGET_STOP' and manifest['error_type'] == 'PilotBudgetExceeded'
    assert manifest['accepted_probe_rows'] == 95
    assert len(evidence['probe_rows']) == 96
    assert evidence['probe_rows'][-1]['validation_status'] == 'BUDGET_STOP'
    assert evidence['probe_rows'][-1]['actions'] is not None
    assert all(run['checkpoints']['selected'] for run in evidence['training_runs'])


def test_timeout_on_episode_callback_keeps_just_completed_episode_log(tmp_path, monkeypatch):
    from experiments import exp_025_neural_policy_pilot as module
    from src.graduation import policy_training

    class Clock:
        now = 0.

        def monotonic(self):
            return self.now

    clock = Clock()
    monkeypatch.setattr(module.time, 'monotonic', clock.monotonic)
    real = policy_training.train_policy

    def delayed(*args, **kwargs):
        callback = kwargs['on_progress']

        def progress(event):
            if event['kind'] == 'episode':
                clock.now = 121.
            callback(event)

        kwargs['on_progress'] = progress
        return real(*args, **kwargs)

    monkeypatch.setattr(policy_training, 'train_policy', delayed)
    output = tmp_path / 'callback_late'
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    assert manifest['status'] == 'BUDGET_STOP'
    first = evidence['training_runs'][0]
    assert first['status'] == 'BUDGET_STOP' and first['episodes_completed'] == 1
    assert len(first['logs']) == 1 and first['training_steps'] == 6
    assert len((output / first['progress_log']).read_text().splitlines()) == 2
    assert first['checkpoints']['initial']['trained'] is False
    assert len(evidence['probe_rows']) == 96 and len(evidence['cp_rows']) == 8


def test_safe_loader_rejects_changed_hash_and_object_arrays(tmp_path):
    import numpy as np
    from experiments.exp_025_neural_policy_pilot import load_checkpoint
    from src.graduation.neural_policy import MaskedMLP

    path = tmp_path / 'state.npz'
    state = MaskedMLP(seed=17).state_dict()
    np.savez_compressed(path, **state)
    actor = load_checkpoint(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert all(np.array_equal(value, actor.state_dict()[name]) for name, value in state.items())
    with pytest.raises(ValueError):
        load_checkpoint(path, expected_sha256='0' * 64)
    state['b1'] = np.array([object()], dtype=object)
    np.savez_compressed(path, **state)
    with pytest.raises(ValueError):
        load_checkpoint(path)


def test_generator_rejects_base_task_collision_before_exposing_splits(monkeypatch):
    from experiments import exp_025_neural_policy_pilot as module
    monkeypatch.setattr(module, '_field_integer', lambda seed, field, low, high: low)
    with pytest.raises(ValueError, match='overlap'):
        module.build_splits()


def test_unknown_solver_status_keeps_all_references_and_cannot_complete(tmp_path, monkeypatch):
    from experiments import exp_025_neural_policy_pilot as module
    from src.graduation.solver import GraduationSolverError

    def unknown(*args, **kwargs):
        raise GraduationSolverError('CP-SAT returned UNKNOWN; no accepted schedule')

    monkeypatch.setattr(module, 'solve_parallel_maintenance', unknown)
    output = tmp_path / 'unknown'
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    assert manifest['status'] == 'FAILED' and manifest['accepted_cp_rows'] == 0
    assert manifest['accepted_probe_rows'] == 96
    assert len(evidence['cp_rows']) == 8
    assert all(row['solver_status'] == 'UNKNOWN' and not row['schedule_accepted']
               and not row['optimum_certified'] and row['payload'] is None for row in evidence['cp_rows'])


@pytest.mark.parametrize('episodes', [0, 65, True, 1.5])
def test_invalid_episode_count_is_rejected_before_creating_output(tmp_path, episodes):
    from experiments.exp_025_neural_policy_pilot import run_experiment
    output = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        run_experiment(output, episodes=episodes)
    assert not output.exists()
