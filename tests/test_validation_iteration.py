"""The single candidate uses validation only and retains incomplete evidence."""

import hashlib
import json

import pytest


def _read(output):
    return json.loads((output / 'results.json').read_bytes())


@pytest.fixture(scope='module')
def tiny(tmp_path_factory):
    from experiments import exp_026_validation_iteration as module

    output = tmp_path_factory.mktemp('validation-iteration') / 'tiny'
    manifest = module.run_experiment(output, episodes=1)
    return output, manifest, _read(output)


def test_tiny_iteration_checks_80_validation_plans_and_eight_references(tiny):
    from experiments import exp_026_validation_iteration as module
    from src.graduation.policy_training import run_policy_episode

    output, manifest, evidence = tiny
    assert manifest['status'] == 'COMPLETED'
    assert manifest['expected_training_runs'] == manifest['completed_training_runs'] == 8
    assert manifest['expected_validation_rows'] == manifest['accepted_validation_rows'] == 80
    assert manifest['expected_cp_rows'] == manifest['accepted_cp_rows'] == 8
    assert manifest['training_steps'] == 48
    assert manifest['config']['max_training_steps'] == 3072
    assert manifest['probe_evaluated'] is False
    assert manifest['research_targets'] == {'paper_reproduction': 'not_achieved', 'graduation_research': 'not_achieved'}
    assert set(evidence['splits']) == {'version', 'generator', 'work_definition', 'training', 'validation'}
    assert len(evidence['training_runs']) == 8 and len(evidence['validation_rows']) == 80
    assert len([r for r in evidence['validation_rows'] if r['method'] in ('none', 'running_mean')]) == 32
    splits = module.build_splits()
    for row in evidence['validation_rows']:
        assert row['validation_status'] == 'PASS' and row['schedule_accepted']
        assert row['check']['accepted'] and row['replay_check']['accepted']
        assert len(row['actions']) == len(row['transitions']) == 6
        assert all(step['action_mask'][step['action']] for step in row['transitions'])
        assert row['payload']['total_reward'] == pytest.approx(-row['payload']['total_tardiness'] / 100)
        if row['method'] in ('none', 'running_mean'):
            run = next(run for run in evidence['training_runs'] if
                       (run['mode'], run['seed'], run['method']) == (row['mode'], row['seed'], row['method']))
            checkpoint = run['checkpoints']['selected']
            actor = module.load_checkpoint(output / checkpoint['path'], expected_sha256=checkpoint['sha256'])
            episode = run_policy_episode(splits['validation'][row['validation_index']], mode=row['mode'],
                                         actor=actor, seed=row['seed'], deterministic=True)
            assert list(episode.actions) == row['actions']
            assert episode.result.total_tardiness == row['payload']['total_tardiness']
    assert all(r['solver_status'] in ('OPTIMAL', 'FEASIBLE') and r['schedule_accepted'] for r in evidence['cp_rows'])
    for run in evidence['training_runs']:
        assert run['episodes_completed'] == 1 and run['training_steps'] == 6
        assert run['checkpoints']['initial']['trained'] is False
        assert run['checkpoints']['selected']['trained'] == (run['selected_episode'] > 0)
        assert len(run['logs']) == 1 and len(run['validation_history']) == 2
        assert run['control_check']['status'] == ('SKIPPED_DIFFERENT_BUDGET' if run['method'] == 'none' else 'NOT_CONTROL')
        events = [json.loads(line) for line in (output / run['progress_log']).read_bytes().splitlines()]
        if run['method'] == 'running_mean':
            assert 'return_baseline' in run['logs'][0]
            assert all('baseline_state' in event for event in events if event['kind'] == 'validation')
            assert all('baseline_state' in event for event in run['validation_history'])
        else:
            assert 'return_baseline' not in run['logs'][0]
        assert run['progress_log_sha256'] == hashlib.sha256((output / run['progress_log']).read_bytes()).hexdigest()
    for relative, digest in manifest['artifacts'].items():
        assert hashlib.sha256((output / relative).read_bytes()).hexdigest() == digest
    assert manifest['diagnosis_sha256'] == hashlib.sha256((output / 'diagnosis.json').read_bytes()).hexdigest()
    assert manifest == json.loads((output / 'manifest.json').read_bytes())


def test_probe_sentinel_is_never_read_and_new_metadata_omits_probe(tmp_path, monkeypatch):
    from experiments import exp_026_validation_iteration as module

    class ForbiddenProbe:
        def __iter__(self):
            raise AssertionError('probe must remain untouched')

        def __getitem__(self, key):
            raise AssertionError('probe must remain untouched')

    original = module._read_reference

    def guarded(*args):
        reference = original(*args)
        reference['splits']['probe'] = ForbiddenProbe()
        return reference

    def forbidden_generator():
        raise AssertionError('even generating probe inputs is forbidden')

    monkeypatch.setattr(module, '_read_reference', guarded)
    monkeypatch.setattr(module.pilot, 'build_splits', forbidden_generator)
    output = tmp_path / 'safe'
    manifest = module.run_experiment(output, episodes=1)
    assert manifest['status'] == 'COMPLETED'
    data = _read(output)
    assert 'probe' not in data['splits'] and 'probe_rows' not in data
    assert data['probe_evaluated'] is False


def test_none_runner_matches_default_training_parameters_and_same_initial_candidate(tiny):
    import numpy as np
    from experiments import exp_026_validation_iteration as module
    from src.graduation.policy_training import train_policy

    output, _, evidence = tiny
    splits = module.build_splits()
    for run in evidence['training_runs']:
        if run['method'] != 'none':
            continue
        default = train_policy(splits['training'], splits['validation'], mode=run['mode'], seed=run['seed'],
                               episodes=1, validation_every=1, hidden_size=16, learning_rate=.01)
        candidate = next(item for item in evidence['training_runs'] if item['method'] == 'running_mean' and
                         (item['mode'], item['seed']) == (run['mode'], run['seed']))
        assert candidate['checkpoints']['initial']['state_sha256'] == run['checkpoints']['initial']['state_sha256']
        for name in ('initial', 'selected', 'final'):
            saved = run['checkpoints'][name]
            restored = module.load_checkpoint(output / saved['path'], expected_sha256=saved['sha256']).state_dict()
            assert all(np.array_equal(value, restored[key]) for key, value in default[name + '_state'].items())
        assert run['selected_episode'] == default['selected_episode']


def _policy_rows():
    return [dict(mode=mode, seed=seed, method=method, validation_index=index,
                 validation_status='PASS', schedule_accepted=True,
                 payload={'total_tardiness': value})
            for mode in ('fixed', 'joint') for seed in (17, 29) for index in range(4)
            for method, value in (('none', 10 if mode == 'fixed' else 4),
                                  ('running_mean', 10 if mode == 'fixed' else 3))]


def test_decision_uses_strict_mean_and_keeps_control_on_ties():
    from experiments.exp_026_validation_iteration import _decisions

    decisions = _decisions(_policy_rows(), complete=True)
    assert decisions['fixed']['selected_method'] == 'none'
    assert decisions['fixed']['mean_validation_tardiness'] == {'none': 10., 'running_mean': 10.}
    assert decisions['joint']['selected_method'] == 'running_mean'
    assert decisions['joint']['mean_validation_tardiness'] == {'none': 4., 'running_mean': 3.}
    assert [row['seed'] for row in decisions['joint']['per_seed']] == [17, 29]


@pytest.mark.parametrize('change', ['incomplete', 'missing', 'duplicate', 'failed'])
def test_partial_or_rejected_denominators_force_stop(change):
    from experiments.exp_026_validation_iteration import _decisions

    rows = _policy_rows()
    if change == 'missing':
        rows.pop()
    if change == 'duplicate':
        rows[-1] = rows[-2].copy()
    if change == 'failed':
        rows[-1]['schedule_accepted'] = False
    decisions = _decisions(rows, complete=change != 'incomplete')
    assert all(item['status'] == 'STOP' and item['selected_method'] is None for item in decisions.values())


def test_repeat_digest_ignores_paths_and_times_and_refuses_overwrite(tiny, tmp_path):
    from experiments import exp_026_validation_iteration as module

    output, first, _ = tiny
    second = module.run_experiment(tmp_path / 'repeat', episodes=1)
    assert first['outcome_digest'] == second['outcome_digest']
    before = (output / 'manifest.json').read_bytes()
    with pytest.raises(FileExistsError):
        module.run_experiment(output, episodes=1)
    assert (output / 'manifest.json').read_bytes() == before


@pytest.mark.parametrize('field,value', [('episodes', 0), ('episodes', 65), ('episodes', True),
    ('episodes', 1.5), ('max_active_seconds', 0), ('max_active_seconds', True),
    ('max_active_seconds', float('nan')), ('max_active_seconds', 121)])
def test_invalid_limits_fail_before_creating_output(tmp_path, field, value):
    from experiments.exp_026_validation_iteration import run_experiment

    output = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        run_experiment(output, **{field: value})
    assert not output.exists()


def test_output_cannot_mutate_reference_archive_directory(tmp_path):
    from experiments.exp_026_validation_iteration import run_experiment

    reference = tmp_path / 'archive'
    reference.mkdir()
    output = reference / 'new-run'
    with pytest.raises(ValueError, match='reference'):
        run_experiment(output, episodes=1, reference_archive=reference)
    assert not output.exists()


def test_failed_training_retains_all_rows_and_completed_callback_evidence(tmp_path, monkeypatch):
    from experiments import exp_026_validation_iteration as module
    from src.graduation import policy_training

    real = policy_training.train_policy

    def interrupted(*args, **kwargs):
        callback = kwargs['on_progress']

        def progress(event):
            callback(event)
            if event['kind'] == 'episode':
                raise RuntimeError('private details are not archived')

        kwargs['on_progress'] = progress
        return real(*args, **kwargs)

    monkeypatch.setattr(policy_training, 'train_policy', interrupted)
    output = tmp_path / 'failure'
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    assert manifest['status'] == 'FAILED' and manifest['completed_training_runs'] == 0
    assert manifest['accepted_validation_rows'] == 48
    assert len(evidence['validation_rows']) == 80 and len(evidence['cp_rows']) == 8
    assert all(run['status'] == 'FAILED' and len(run['logs']) == 1 for run in evidence['training_runs'])
    assert all(run['checkpoints']['initial']['trained'] is False for run in evidence['training_runs'])
    assert all(value['status'] == 'STOP' for value in manifest['decisions'].values())
    assert b'private details' not in (output / 'results.json').read_bytes()


def test_diagnostic_failure_prevents_training_but_keeps_all_denominators(tmp_path, monkeypatch):
    from experiments import exp_026_validation_iteration as module

    def rejected(*args, **kwargs):
        raise ValueError('tampered archive')

    monkeypatch.setattr(module, 'diagnose_validation', rejected)
    manifest = module.run_experiment(tmp_path / 'rejected', episodes=1)
    evidence = _read(tmp_path / 'rejected')
    assert manifest['status'] == 'FAILED' and manifest['completed_training_runs'] == 0
    assert all(run['status'] == 'NOT_RUN' for run in evidence['training_runs'])
    assert manifest['accepted_validation_rows'] == manifest['accepted_cp_rows'] == 0
    assert len(evidence['validation_rows']) == 80 and len(evidence['cp_rows']) == 8


def test_timeout_callback_preserves_just_completed_update(tmp_path, monkeypatch):
    from experiments import exp_026_validation_iteration as module
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
    output = tmp_path / 'timeout'
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    assert manifest['status'] == 'BUDGET_STOP'
    run = evidence['training_runs'][0]
    assert run['status'] == 'BUDGET_STOP' and run['episodes_completed'] == 1
    assert run['training_steps'] == 6 and len(run['logs']) == 1
    assert len((output / run['progress_log']).read_bytes().splitlines()) == 2
    assert run['checkpoints']['initial']['trained'] is False
    assert 'final' not in run['checkpoints']
    assert len(evidence['validation_rows']) == 80 and len(evidence['cp_rows']) == 8


def test_deadline_after_manifest_write_cannot_report_success(tmp_path, monkeypatch):
    from experiments import exp_026_validation_iteration as module

    class Clock:
        now = 0.

        def monotonic(self):
            return self.now

    clock = Clock()
    monkeypatch.setattr(module.time, 'monotonic', clock.monotonic)
    real = module._write_json

    def slow_write(path, value):
        real(path, value)
        if path.name == 'manifest.json':
            clock.now = 121.

    monkeypatch.setattr(module, '_write_json', slow_write)
    output = tmp_path / 'last-write'
    manifest = module.run_experiment(output, episodes=1)
    assert manifest['status'] == 'BUDGET_STOP'
    assert all(value['status'] == 'STOP' for value in manifest['decisions'].values())
    assert manifest == json.loads((output / 'manifest.json').read_bytes())


def test_control_64_parameter_hashes_must_match_reference_without_training():
    from experiments import exp_026_validation_iteration as module

    reference = module._read_reference(module.DEFAULT_REFERENCE, lambda: None)
    old = reference['runs'][0]
    run = dict(method='none', mode=old['mode'], seed=old['seed'], checkpoints=old['checkpoints'].copy(),
               selected_episode=old['selected_episode'])
    checked = module._control_check(run, reference, episodes=64, check_budget=lambda: None)
    assert checked['status'] == 'PASS'
    assert checked['initial_match'] and checked['selected_match'] and checked['final_match']
    run['checkpoints']['final'] = dict(run['checkpoints']['final'], state_sha256='0' * 64)
    with pytest.raises(ValueError, match='control'):
        module._control_check(run, reference, episodes=64, check_budget=lambda: None)


def test_initial_control_mismatch_is_not_hidden_by_tiny_budget():
    from experiments import exp_026_validation_iteration as module

    reference = module._read_reference(module.DEFAULT_REFERENCE, lambda: None)
    old = reference['runs'][0]
    checkpoints = old['checkpoints'].copy()
    checkpoints['initial'] = dict(checkpoints['initial'], state_sha256='0' * 64)
    run = dict(method='none', mode=old['mode'], seed=old['seed'], checkpoints=checkpoints,
               selected_episode=old['selected_episode'])
    with pytest.raises(ValueError, match='control'):
        module._control_check(run, reference, episodes=1, check_budget=lambda: None)


def test_candidate_must_start_from_identical_frozen_parameters():
    from experiments import exp_026_validation_iteration as module

    reference = module._read_reference(module.DEFAULT_REFERENCE, lambda: None)
    old = reference['runs'][0]
    checkpoints = old['checkpoints'].copy()
    checkpoints['initial'] = dict(checkpoints['initial'], state_sha256='0' * 64)
    run = dict(method='running_mean', mode=old['mode'], seed=old['seed'], checkpoints=checkpoints,
               selected_episode=old['selected_episode'])
    with pytest.raises(ValueError, match='initial'):
        module._control_check(run, reference, episodes=1, check_budget=lambda: None)


def test_unknown_cp_status_retains_references_and_stops_selection(tmp_path, monkeypatch):
    from experiments import exp_026_validation_iteration as module
    from src.graduation.solver import GraduationSolverError

    def unknown(*args, **kwargs):
        raise GraduationSolverError('CP-SAT returned UNKNOWN; no accepted schedule')

    monkeypatch.setattr(module, 'solve_parallel_maintenance', unknown)
    output = tmp_path / 'unknown'
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    assert manifest['status'] == 'FAILED' and manifest['accepted_cp_rows'] == 0
    assert manifest['accepted_validation_rows'] == 80
    assert len(evidence['cp_rows']) == 8
    assert all(row['solver_status'] == 'UNKNOWN' and not row['schedule_accepted'] and
               row['payload'] is None and not row['optimum_certified'] for row in evidence['cp_rows'])
    assert all(value['status'] == 'STOP' for value in manifest['decisions'].values())


@pytest.mark.parametrize('status', ['OPTIMAL', 'FEASIBLE'])
def test_candidate_beating_cp_optimal_fails_but_feasible_is_not_optimal(tmp_path, monkeypatch, status):
    from experiments import exp_026_validation_iteration as module
    from src.graduation.rules import run_maintenance_rule_episode

    def poor_reference(data, *, mode, time_limit, num_workers, seed):
        assert 0 < time_limit <= 1 and num_workers == 1 and seed == 42
        result = max((run_maintenance_rule_episode(data, mode=mode, rule='Random', seed=s).result
                      for s in range(16)), key=lambda item: item.total_tardiness)
        result.solver_status = status
        result.solver_objective_value = float(result.total_tardiness)
        result.solver_objective_bound = float(result.total_tardiness) if status == 'OPTIMAL' else 0.
        result.solver_gap = 0. if status == 'OPTIMAL' else result.total_tardiness / max(1, result.total_tardiness)
        result.solver_wall_time = .001
        return result

    monkeypatch.setattr(module, 'solve_parallel_maintenance', poor_reference)
    output = tmp_path / status
    manifest = module.run_experiment(output, episodes=1)
    evidence = _read(output)
    better = [row for row in evidence['validation_rows'] if row['cp_comparison']['tardiness_difference'] < 0]
    assert better
    if status == 'OPTIMAL':
        assert manifest['status'] == 'FAILED'
        assert all(not row['schedule_accepted'] for row in better)
    else:
        assert manifest['status'] == 'COMPLETED'
        assert all(row['schedule_accepted'] for row in better)
