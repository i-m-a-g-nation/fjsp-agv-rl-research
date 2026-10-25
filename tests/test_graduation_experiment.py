import csv
import hashlib
import json

import pytest


def read_rows(output):
    with (output / 'raw.csv').open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_native_reference_matrix_exports_verified_inputs_schedules_and_objective_diagnostics(tmp_path):
    from experiments.exp_021_graduation_solver_check import run_experiment
    output = tmp_path / 'run'
    manifest = run_experiment(output)
    assert manifest['status'] == 'COMPLETED'
    assert manifest['expected_runs'] == manifest['passed_runs'] == 24
    rows = read_rows(output)
    literal = {('one_machine', 'fixed'): '4', ('one_machine', 'joint'): '0',
               ('two_machines', 'fixed'): '6', ('two_machines', 'joint'): '0',
               ('idle_machine', 'fixed'): '2', ('idle_machine', 'joint'): '2'}
    for row in rows:
        assert row['solver_status'] == 'OPTIMAL' and row['schedule_accepted'] == 'True'
        assert row['total_tardiness'] == row['reference_total_tardiness']
        assert float(row['solver_objective_value']) == float(row['total_tardiness'])
        assert float(row['solver_objective_bound']) == float(row['total_tardiness'])
        assert float(row['solver_gap']) == 0
        if (row['case'], row['mode']) in literal:
            assert row['total_tardiness'] == literal[row['case'], row['mode']]
    assert len(list((output / 'inputs').glob('*.json'))) == 12
    assert len(list((output / 'schedules').glob('*.json'))) == 24
    for relative, digest in manifest['artifacts'].items():
        assert hashlib.sha256((output / relative).read_bytes()).hexdigest() == digest
    assert 'ortools' in manifest['runtime']['packages']
    assert 'src/graduation/solver.py' in manifest['runtime']['source_hashes']


def test_same_outcome_digest_allows_different_valid_record_order(tmp_path, monkeypatch):
    from experiments import exp_021_graduation_solver_check as module
    first = module.run_experiment(tmp_path / 'first')
    original = module.solve_parallel_maintenance
    def reordered(*args, **kwargs):
        result = original(*args, **kwargs)
        result.records.reverse()
        return result
    monkeypatch.setattr(module, 'solve_parallel_maintenance', reordered)
    second = module.run_experiment(tmp_path / 'second')
    assert first['outcome_digest'] == second['outcome_digest']
    assert first['input_hashes'] == second['input_hashes']


@pytest.mark.parametrize('fault', ['missing_maintenance', 'raised', 'feasible', 'wrong_reference'])
def test_invalid_results_have_no_accepted_metrics_and_incomplete_validation_fails_cli(tmp_path, monkeypatch, fault):
    from experiments import exp_021_graduation_solver_check as module
    cases = module.build_cases()
    monkeypatch.setattr(module, 'build_cases', lambda: cases[:1])
    original = module.solve_parallel_maintenance
    original_reference = module.enumerate_parallel_maintenance
    def altered(*args, **kwargs):
        if fault == 'raised': raise RuntimeError('controlled solver failure')
        result = original(*args, **kwargs)
        if fault == 'missing_maintenance': result.maintenance_records.clear()
        if fault == 'feasible': result.solver_status = 'FEASIBLE'
        return result
    def wrong_reference(*args, **kwargs):
        result = original_reference(*args, **kwargs)
        result.total_tardiness += 1
        return result
    monkeypatch.setattr(module, 'solve_parallel_maintenance', altered)
    if fault == 'wrong_reference': monkeypatch.setattr(module, 'enumerate_parallel_maintenance', wrong_reference)
    output = tmp_path / fault
    assert module.main(['--output-dir', str(output)]) == 1
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'FAILED' and manifest['passed_runs'] == 0
    rows = read_rows(output)
    assert all(row['validation_status'] == 'FAIL' and row['error'] for row in rows)
    if fault in ('missing_maintenance', 'raised'):
        assert all(row['total_tardiness'] == row['makespan'] == row['solver_objective_value'] == '' for row in rows)
        assert all(row['schedule_accepted'] == 'False' for row in rows)
    if fault == 'feasible':
        assert all(row['schedule_accepted'] == 'True' and row['solver_status'] == 'FEASIBLE' for row in rows)
    if fault == 'wrong_reference':
        assert all(row['reference_total_tardiness'] == '' for row in rows)


def test_existing_output_is_preserved_and_successful_cli_is_runnable(tmp_path):
    from experiments.exp_021_graduation_solver_check import main, run_experiment
    output = tmp_path / 'existing'
    output.mkdir()
    (output / 'sentinel').write_text('keep', encoding='utf-8')
    with pytest.raises(FileExistsError): run_experiment(output)
    assert (output / 'sentinel').read_text() == 'keep'
    assert main(['--output-dir', str(tmp_path / 'cli')]) == 0
