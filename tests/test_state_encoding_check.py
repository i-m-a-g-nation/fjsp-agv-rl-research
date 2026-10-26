"""Transport evidence must be independently restorable and reject failed rows."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from src.graduation.data import (
    MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask, to_fjsp_instance,
)
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult
from src.scheduling.encoding import ScheduleRecord


def _read(output):
    return json.loads((output / 'results.json').read_text(encoding='utf-8'))


def _restore_data(raw):
    return ParallelMaintenanceInstance(
        tuple(ProductionTask(**task) for task in raw['tasks']), raw['num_machines'],
        tuple(MaintenanceRequirement(**item) for item in raw['maintenance']))


def _restore_plan(data, payload):
    plan = payload['plan']
    return MaintenanceScheduleResult(
        instance=to_fjsp_instance(data),
        records=[ScheduleRecord(**record) for record in plan['records']],
        maintenance_records=[MaintenanceRecord(**record) for record in plan['maintenance_records']],
        makespan=payload['makespan'], total_tardiness=payload['total_tardiness'],
        **{field: plan[field] for field in ('solver_status', 'solver_objective_value',
            'solver_objective_bound', 'solver_gap', 'solver_wall_time')})


def _check_snapshot(snapshot, expected_tails):
    """Literal column interpretation does not trust the encoder's mapping."""
    from src.graduation.rl_environment import ConstructionObservation
    from src.graduation.state_encoding import TypedStateEncoding, decode_construction_observation

    raw, encoded = snapshot['observation'], snapshot['encoded']
    assert snapshot['machine_tails'] == expected_tails
    assert all(type(value) is int for value in snapshot['machine_tails'])
    assert len(encoded['rows']) == 28
    for index, row in enumerate(encoded['rows']):
        assert len(row) == 13 and all(type(value) is float for value in row)
        if index < 24:
            assert row == raw['task_features'][index] + [0.0] * 7 + [1.0, 0.0, float(raw['task_presence'][index])]
        else:
            machine = index - 24
            assert row == [0.0] * 3 + raw['machine_features'][machine] + [0.0, 1.0, float(raw['machine_presence'][machine])]
    for field in ('mode', 'status', 'steps', 'scale', 'action_mask'):
        assert encoded[field] == raw[field]
    restored = TypedStateEncoding(**dict(encoded, rows=tuple(tuple(row) for row in encoded['rows']),
        action_mask=tuple(encoded['action_mask'])))
    expected = ConstructionObservation(**dict(raw,
        task_features=tuple(tuple(row) for row in raw['task_features']),
        machine_features=tuple(tuple(row) for row in raw['machine_features']),
        task_presence=tuple(raw['task_presence']), machine_presence=tuple(raw['machine_presence']),
        action_mask=tuple(raw['action_mask'])))
    assert decode_construction_observation(restored) == expected


def test_24_rows_archive_literal_encodings_and_independently_accepted_replay_plans(tmp_path):
    from experiments.exp_024_state_encoding_check import run_experiment

    output = tmp_path / 'run'
    manifest = run_experiment(output)
    evidence = _read(output)
    assert manifest['status'] == 'COMPLETED'
    assert manifest['accepted_runs'] == manifest['expected_runs'] == len(evidence['rows']) == 24
    assert evidence['purpose'] == 'state_encoding_transport_replay_validation'
    assert evidence['research_status'] == manifest['research_status'] == 'not_achieved'
    assert evidence['matrix_consuming_policy'] is False
    assert {(row['case'], row['mode'], row['rule']) for row in evidence['rows']} == {
        (case, mode, rule) for case in ('one_machine', 'two_machines', 'idle_machine', 'late_maintenance')
        for mode in ('fixed', 'joint') for rule in ('EDD', 'SPT', 'Random')}
    for row in evidence['rows']:
        data = _restore_data(evidence['inputs'][row['case']])
        assert row['validation_status'] == 'PASS' and row['schedule_accepted'] is True
        assert row['error_type'] is None
        assert row['baseline'] == row['replay']
        assert row['baseline_check'] == row['replay_check'] == {'accepted': True, 'issues': []}
        assert row['seed'] == 42
        assert len(row['trace']) == len(row['actions']) == len(data.tasks) + data.num_machines
        for payload in (row['baseline'], row['replay']):
            result = _restore_plan(data, payload)
            assert check_parallel_maintenance_feasibility(result, data, mode=row['mode']) == (True, [])
            completions = {record.job_id: record.end for record in result.records}
            independently_computed = sum(max(0, completions[task.job_id] - task.due_date) for task in data.tasks)
            assert payload['total_tardiness'] == payload['recomputed_total_tardiness'] == independently_computed
            assert payload['total_reward'] == pytest.approx(-independently_computed / 100)
            assert payload['total_reward'] == sum(payload['rewards'])
            assert payload['actions'] == row['actions']
            assert all(payload['plan'][field] is None for field in ('solver_status', 'solver_objective_value',
                'solver_objective_bound', 'solver_gap', 'solver_wall_time'))
        plan = row['baseline']['plan']
        tails = [0] * data.num_machines
        for index, transition in enumerate(row['trace']):
            assert transition['step'] == index and transition['action'] == row['actions'][index]
            assert transition['baseline_before'] == transition['replay_before']
            assert transition['baseline_after'] == transition['replay_after']
            _check_snapshot(transition['baseline_before'], tails)
            _check_snapshot(transition['replay_before'], tails)
            action = transition['action']
            if action < 96:
                job, machine = divmod(action, 4)
                tails[machine] = next(record['end'] for record in plan['records'] if record['job_id'] == job)
            else:
                machine = action - 96
                tails[machine] = next(record['end'] for record in plan['maintenance_records'] if record['machine_id'] == machine)
            _check_snapshot(transition['baseline_after'], tails)
            _check_snapshot(transition['replay_after'], tails)
            assert transition['baseline_reward'] == transition['replay_reward'] == row['replay']['rewards'][index]
        assert row['trace'][-1]['replay_after']['observation']['status'] == 'TERMINATED'
        assert not any(row['trace'][-1]['replay_after']['observation']['action_mask'])
    assert manifest == json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    assert {'src/graduation/state_encoding.py', 'src/graduation/rl_environment.py',
        'experiments/exp_022_graduation_rule_smoke.py', 'experiments/exp_024_state_encoding_check.py'} <= set(manifest['runtime']['source_hashes'])
    root = Path(__file__).resolve().parents[1]
    for relative, digest in manifest['runtime']['source_hashes'].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
    assert manifest['artifacts']['results.json'] == hashlib.sha256((output / 'results.json').read_bytes()).hexdigest()


def test_fresh_runs_repeat_digest_and_cli_refuses_overwrite(tmp_path):
    from experiments.exp_024_state_encoding_check import main, run_experiment

    first_path, second_path = tmp_path / 'one', tmp_path / 'two'
    first = run_experiment(first_path)
    original = {path.name: path.read_bytes() for path in first_path.iterdir()}
    second = run_experiment(second_path)
    assert first['outcome_digest'] == second['outcome_digest']
    assert (first_path / 'results.json').read_bytes() == (second_path / 'results.json').read_bytes()
    with pytest.raises(FileExistsError):
        run_experiment(first_path)
    assert main(['--output-dir', str(first_path)]) == 1
    assert {path.name: path.read_bytes() for path in first_path.iterdir()} == original
    assert main(['--output-dir', str(tmp_path / 'cli')]) == 0


@pytest.mark.parametrize('fault', ['missing_maintenance', 'certificate', 'reward', 'short_actions', 'raised'])
def test_invalid_baselines_retain_failures_without_accepted_metrics(tmp_path, monkeypatch, fault):
    from experiments import exp_024_state_encoding_check as module

    original = module.run_maintenance_rule_episode

    def altered(data, **kwargs):
        if kwargs['rule'] != 'EDD':
            return original(data, **kwargs)
        if fault == 'raised':
            raise RuntimeError('private failure content must not be serialized')
        episode = original(data, **kwargs)
        if fault == 'missing_maintenance':
            episode.result.maintenance_records.clear()
        elif fault == 'certificate':
            episode.result.solver_status = 'OPTIMAL'
        elif fault == 'reward':
            return replace(episode, total_reward=episode.total_reward + 1)
        elif fault == 'short_actions':
            return replace(episode, actions=episode.actions[:-1])
        return episode

    monkeypatch.setattr(module, 'run_maintenance_rule_episode', altered)
    output = tmp_path / fault
    assert module.main(['--output-dir', str(output)]) == 1
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    rows = _read(output)['rows']
    assert manifest['status'] == 'FAILED' and manifest['expected_runs'] == 24 and manifest['accepted_runs'] == 16
    assert len(rows) == 24
    for row in rows:
        if row['rule'] == 'EDD':
            assert row['validation_status'] == 'FAIL' and row['schedule_accepted'] is False
            assert row['baseline'] is row['replay'] is None
            assert row['error_type'] in ('ValueError', 'RuntimeError')
        else:
            assert row['validation_status'] == 'PASS' and row['schedule_accepted'] is True
    assert b'private failure content' not in (output / 'results.json').read_bytes()
    if fault == 'missing_maintenance':
        assert any(issue['code'] == 'MISSING_MAINTENANCE' for row in rows if row['rule'] == 'EDD'
            for issue in row['baseline_check']['issues'])


@pytest.mark.parametrize('fault', ['encoder', 'decoder', 'matching_wrong_mapping', 'raised_decoder', 'nan_encoder'])
def test_bad_transports_retain_raw_snapshots_and_reject_every_row(tmp_path, monkeypatch, fault):
    from experiments import exp_024_state_encoding_check as module

    encode, decode = module.encode_construction_observation, module.decode_construction_observation

    def shifted(encoded, amount):
        rows = tuple((row[0] + amount, *row[1:]) if index == 0 else row
            for index, row in enumerate(encoded.rows))
        return replace(encoded, rows=rows)

    if fault in ('encoder', 'matching_wrong_mapping'):
        monkeypatch.setattr(module, 'encode_construction_observation', lambda observation: shifted(encode(observation), 1.0))
    if fault == 'matching_wrong_mapping':
        monkeypatch.setattr(module, 'decode_construction_observation', lambda encoded: decode(shifted(encoded, -1.0)))
    elif fault == 'decoder':
        def changed_mask(encoded):
            observation = decode(encoded)
            return replace(observation, action_mask=(not observation.action_mask[0], *observation.action_mask[1:]))
        monkeypatch.setattr(module, 'decode_construction_observation', changed_mask)
    elif fault == 'raised_decoder':
        def rejected(_):
            raise ValueError('controlled decoder failure')
        monkeypatch.setattr(module, 'decode_construction_observation', rejected)
    elif fault == 'nan_encoder':
        def nonfinite(observation):
            encoded = encode(observation)
            rows = ((float('nan'), *encoded.rows[0][1:]), *encoded.rows[1:])
            object.__setattr__(encoded, 'rows', rows)
            return encoded
        monkeypatch.setattr(module, 'encode_construction_observation', nonfinite)
    output = tmp_path / fault
    manifest = module.run_experiment(output)
    assert manifest['status'] == 'FAILED' and manifest['accepted_runs'] == 0
    for row in _read(output)['rows']:
        assert row['schedule_accepted'] is False and row['baseline'] is row['replay'] is None
        assert row['error_type'] == 'ValueError'
        snapshot = row['trace'][0]['baseline_before']
        assert snapshot['observation']['status'] == 'ACTIVE'
        assert snapshot['observation']['task_features'][0]
        assert snapshot['encoded'] is not None
        if fault == 'nan_encoder':
            assert snapshot['encoded']['rows'][0][0] == {'invalid_float': 'nan'}


def test_noninteger_exact_clocks_are_not_accepted_as_float_features(tmp_path, monkeypatch):
    from experiments import exp_024_state_encoding_check as module

    class FloatClockEnv(module.ParallelMaintenanceEnv):
        @property
        def machine_tails(self):
            return tuple(float(value) for value in super().machine_tails)

    monkeypatch.setattr(module, 'ParallelMaintenanceEnv', FloatClockEnv)
    manifest = module.run_experiment(tmp_path / 'clocks')
    assert manifest['status'] == 'FAILED' and manifest['accepted_runs'] == 0
    assert all(row['error_type'] == 'ValueError' for row in _read(tmp_path / 'clocks')['rows'])


def test_invalid_replay_plan_cannot_reuse_baseline_acceptance(tmp_path, monkeypatch):
    from experiments import exp_024_state_encoding_check as module

    original_env = module.ParallelMaintenanceEnv

    class BadReplayEnv(original_env):
        def get_result(self):
            result = super().get_result()
            result.maintenance_records.clear()
            return result

    constructed = 0

    def alternating_env(data, *, mode):
        nonlocal constructed
        constructed += 1
        return (original_env if constructed % 2 else BadReplayEnv)(data, mode=mode)

    monkeypatch.setattr(module, 'ParallelMaintenanceEnv', alternating_env)
    output = tmp_path / 'invalid_replay'
    manifest = module.run_experiment(output)
    assert manifest['status'] == 'FAILED' and manifest['accepted_runs'] == 0
    for row in _read(output)['rows']:
        assert row['baseline_check'] == {'accepted': True, 'issues': []}
        assert row['replay_check']['accepted'] is False
        assert any(issue['code'] == 'MISSING_MAINTENANCE' for issue in row['replay_check']['issues'])
        assert row['baseline'] is row['replay'] is None and row['schedule_accepted'] is False
        assert len(row['trace']) == len(row['actions'])
        assert row['error_type'] == 'ValueError' and row['failure_stage'] == 'terminal_plans'


def test_invalid_dictionary_keys_preserve_rejected_trace_and_manifest(tmp_path,monkeypatch):
    from experiments import exp_024_state_encoding_check as module
    encode=module.encode_construction_observation
    def malformed(observation):
        encoded=encode(observation)
        rows=(({(1,2):0.0},*encoded.rows[0][1:]),*encoded.rows[1:])
        object.__setattr__(encoded,'rows',rows)
        return encoded
    monkeypatch.setattr(module,'encode_construction_observation',malformed)
    output=tmp_path/'bad_keys'
    manifest=module.run_experiment(output)
    assert manifest['status']=='FAILED' and manifest['accepted_runs']==0
    for row in _read(output)['rows']:
        assert row['baseline'] is row['replay'] is None and row['schedule_accepted'] is False
        assert row['error_type']=='TypeError'
        rejected=row['trace'][0]['baseline_before']['encoded']['rows'][0][0]
        assert rejected=={'invalid_mapping':[{'key_type':'tuple','key':[1,2],'value':0.0}]}
    assert (output/'manifest.json').is_file()
