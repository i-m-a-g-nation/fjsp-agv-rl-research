"""The bounded development matrix must preserve evidence, including failures."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from src.graduation import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation import MaintenanceRecord, MaintenanceScheduleResult, check_parallel_maintenance_feasibility, to_fjsp_instance
from src.scheduling.encoding import ScheduleRecord


def read_results(output):
    return json.loads((output / 'results.json').read_text(encoding='utf-8'))


def test_24_development_rows_save_inputs_actions_and_independently_checkable_plans(tmp_path):
    from experiments.exp_022_graduation_rule_smoke import run_experiment
    output = tmp_path / 'run'
    manifest = run_experiment(output)
    evidence = read_results(output)
    assert manifest['status'] == 'COMPLETED'
    assert manifest['expected_runs'] == manifest['accepted_runs'] == 24
    assert manifest['purpose'] == evidence['purpose'] == 'r2_development_validation'
    assert manifest['research_status'] == evidence['research_status'] == 'not_achieved'
    assert len(evidence['inputs']) == 4 and len(evidence['rows']) == 24
    assert {(row['case'], row['mode'], row['rule']) for row in evidence['rows']} == {
        (case, mode, rule) for case in ('one_machine', 'two_machines', 'idle_machine', 'late_maintenance')
        for mode in ('fixed', 'joint') for rule in ('EDD', 'SPT', 'Random')}
    for row in evidence['rows']:
        raw = evidence['inputs'][row['case']]
        data = ParallelMaintenanceInstance(tuple(ProductionTask(**task) for task in raw['tasks']), raw['num_machines'],
            tuple(MaintenanceRequirement(**item) for item in raw['maintenance']))
        plan = row['plan']
        result = MaintenanceScheduleResult(instance=to_fjsp_instance(data),
            records=[ScheduleRecord(**record) for record in plan['records']],
            maintenance_records=[MaintenanceRecord(**record) for record in plan['maintenance_records']],
            makespan=row['makespan'], total_tardiness=row['total_tardiness'])
        assert check_parallel_maintenance_feasibility(result, data, mode=row['mode']) == (True, [])
        assert row['schedule_accepted'] is True and row['validation_status'] == 'PASS'
        assert row['g1_check'] == {'accepted': True, 'issues': []}
        assert row['seed'] == 42 and len(row['actions']) == len(data.tasks) + data.num_machines
        assert row['total_tardiness'] == row['recomputed_total_tardiness']
        assert row['total_reward'] == pytest.approx(-row['total_tardiness'] / 100)
        assert plan['solver_status'] is None and plan['solver_objective_value'] is None
        if row['rule'] != 'Random' and row['case'] in ('one_machine', 'two_machines'):
            assert row['total_tardiness'] == {('one_machine', 'fixed'): 4, ('one_machine', 'joint'): 0,
                ('two_machines', 'fixed'): 6, ('two_machines', 'joint'): 0}[(row['case'], row['mode'])]
        if row['case'] == 'late_maintenance':
            assert row['makespan'] == 1 and row['total_tardiness'] == 0
            assert plan['maintenance_records'][0]['end'] == 4
    saved_manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest == saved_manifest
    assert manifest['runtime']['python'] and manifest['runtime']['git_head']
    assert 'src/graduation/rules.py' in manifest['runtime']['source_hashes']
    assert 'src/graduation/rl_environment.py' in manifest['runtime']['source_hashes']
    for relative, digest in manifest['runtime']['source_hashes'].items():
        assert hashlib.sha256(Path(relative).read_bytes()).hexdigest() == digest
    assert manifest['artifacts']['results.json'] == hashlib.sha256((output / 'results.json').read_bytes()).hexdigest()


def test_fresh_directories_repeat_digest_and_existing_artifacts_are_untouched(tmp_path):
    from experiments.exp_022_graduation_rule_smoke import run_experiment, main
    first_path, second_path = tmp_path / 'first', tmp_path / 'second'
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


@pytest.mark.parametrize('fault', ['missing_maintenance', 'bad_record', 'bad_maintenance', 'bad_result', 'nan', 'raised'])
def test_failed_rows_keep_the_24_denominator_and_clear_metrics_and_plans(tmp_path, monkeypatch, fault):
    from experiments import exp_022_graduation_rule_smoke as module
    original = module.run_maintenance_rule_episode

    def altered(data, **kwargs):
        if kwargs['rule'] != 'EDD':
            return original(data, **kwargs)
        if fault == 'raised':
            raise RuntimeError('controlled failure ' + 'x' * 5000)
        episode = original(data, **kwargs)
        if fault == 'bad_result':
            return replace(episode, result=None)
        if fault == 'missing_maintenance':
            episode.result.maintenance_records.clear()
        if fault == 'bad_record':
            episode.result.records[0] = object()
        if fault == 'bad_maintenance':
            episode.result.maintenance_records = object()
        if fault == 'nan':
            return replace(episode, total_reward=float('nan'))
        return episode

    monkeypatch.setattr(module, 'run_maintenance_rule_episode', altered)
    output = tmp_path / fault
    assert module.main(['--output-dir', str(output)]) == 1
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    rows = read_results(output)['rows']
    assert manifest['status'] == 'FAILED' and manifest['expected_runs'] == 24 and manifest['accepted_runs'] == 16
    assert len(rows) == 24
    for row in rows:
        if row['rule'] == 'EDD':
            assert row['validation_status'] == 'FAIL' and row['schedule_accepted'] is False
            assert row['plan'] is row['total_tardiness'] is row['recomputed_total_tardiness'] is row['makespan'] is row['total_reward'] is None
            assert row['error'] and len(row['error']) <= 1100
        else:
            assert row['validation_status'] == 'PASS' and row['schedule_accepted'] is True
