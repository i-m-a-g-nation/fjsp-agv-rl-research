import json

import pytest

from experiments.common import record_from_run, run_solver_once, run_solver_suite, write_results_csv
from src.data.instance import FJSPInstance
from src.solvers.baselines import fifo_solve


def instance(duration=5):
    return FJSPInstance.from_jobs_array([[[(0, duration)]]], num_machines=1)


def test_runner_requires_original_instance_before_solver_execution():
    with pytest.raises(TypeError, match='expected_instance'):
        run_solver_once('unbound', lambda: fifo_solve(instance()))


def test_runner_rejects_schedule_for_another_problem():
    run = run_solver_once('substitution', lambda: fifo_solve(instance(1)), expected_instance=instance(5))
    assert not run.feasible
    assert 'INSTANCE_MISMATCH' in run.note


def test_runner_detects_mutation_even_if_solver_changes_input_and_plan():
    data = instance(5)

    def solver():
        # Bypass normal immutability to exercise the runner's independent snapshot.
        object.__setattr__(data, 'jobs', instance(1).jobs)
        return fifo_solve(data)

    run = run_solver_once('mutated', solver, expected_instance=data)
    assert not run.feasible
    assert 'INSTANCE_CHANGED' in run.note


def test_suite_keeps_original_snapshot_across_algorithms():
    data = instance(5)

    def mutate():
        object.__setattr__(data, 'jobs', instance(1).jobs)
        return fifo_solve(data)

    runs = run_solver_suite([('mutate', mutate), ('later', lambda: fifo_solve(data))], expected_instance=data)
    assert not any(run.feasible for run in runs)


def test_suite_rejects_input_mutation_even_with_original_valid_output():
    data = instance(5)
    output = fifo_solve(instance(5))
    def mutate():
        object.__setattr__(data, 'jobs', instance(1).jobs)
        return output
    runs = run_solver_suite([('mutate', mutate)], expected_instance=data)
    assert not runs[0].feasible
    assert 'INSTANCE_CHANGED' in runs[0].note


def write_run(tmp_path):
    data = instance()
    run = run_solver_once('FIFO', lambda: fifo_solve(data), expected_instance=data)
    path = tmp_path / 'run.csv'
    write_results_csv(path, [record_from_run('unit', 'one', run)])
    return path


def test_csv_sidecar_replays_full_schedule_and_preserves_runtime(tmp_path):
    from experiments.artifacts import recheck_results_csv
    path = write_run(tmp_path)
    evidence = json.loads(path.with_suffix('.evidence.json').read_text(encoding='utf-8'))
    assert evidence['version'] == 1
    assert evidence['runtime']['packages']['ortools']
    assert evidence['source_sha256']['src/data/instance.py']
    assert evidence['rows'][0]['run']['expected_instance']['jobs'] == [[[[0, 5]]]]
    assert evidence['rows'][0]['run']['result']['records'][0]['end'] == 5
    assert recheck_results_csv(path)['validated_schedules'] == 1


def test_writer_refuses_overwrite_of_either_artifact(tmp_path):
    path = write_run(tmp_path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_results_csv(path, [])
    assert path.read_bytes() == before
    path.unlink()
    with pytest.raises(FileExistsError):
        write_results_csv(path, [])


def test_recheck_rejects_modified_csv_or_missing_sidecar(tmp_path):
    from experiments.artifacts import recheck_results_csv
    path = write_run(tmp_path)
    original = path.read_bytes()
    path.write_bytes(original.replace(b',5,PASS,', b',1,PASS,'))
    with pytest.raises(ValueError, match='hash'):
        recheck_results_csv(path)
    path.write_bytes(original)
    path.with_suffix('.evidence.json').unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        recheck_results_csv(path)


def test_recheck_rejects_illegal_plan_even_with_rehashed_document(tmp_path):
    from experiments.artifacts import recheck_results_csv
    path = write_run(tmp_path)
    sidecar = path.with_suffix('.evidence.json')
    evidence = json.loads(sidecar.read_text(encoding='utf-8'))
    evidence['rows'][0]['run']['result']['records'][0]['start'] = -1
    sidecar.write_text(json.dumps(evidence), encoding='utf-8')
    with pytest.raises(ValueError, match='schedule|feasibility'):
        recheck_results_csv(path)


def test_writer_does_not_certify_metric_only_rows(tmp_path):
    from experiments.artifacts import recheck_results_csv
    from experiments.common import ExperimentRecord
    path = tmp_path / 'metrics.csv'
    row = ExperimentRecord('unit', 'one', 'manual', 5, True, 0.1, 'PASS')
    write_results_csv(path, [row])
    with pytest.raises(ValueError, match='evidence'):
        recheck_results_csv(path)


def test_edited_result_after_execution_cannot_change_recorded_evidence(tmp_path):
    from experiments.artifacts import recheck_results_csv
    data = instance()
    result = fifo_solve(data)
    run = run_solver_once('FIFO', lambda: result, expected_instance=data)
    record = record_from_run('unit', 'one', run)
    result.records[0].end = 1
    path = tmp_path / 'run.csv'
    write_results_csv(path, [record])
    assert recheck_results_csv(path)['validated_schedules'] == 1


def test_failed_solver_is_archived_without_fake_feasible_schedule(tmp_path):
    from experiments.artifacts import recheck_results_csv
    def fail():
        raise RuntimeError('expected failure')
    run = run_solver_once('failure', fail, expected_instance=instance())
    path = tmp_path / 'failed.csv'
    write_results_csv(path, [record_from_run('unit', 'one', run)])
    report = recheck_results_csv(path)
    assert report['validated_schedules'] == 0
    assert report['failed_runs'] == 1


@pytest.mark.parametrize('module_name', ['exp_001_toy_instance', 'exp_002_solver_check'])
def test_basic_experiment_cli_writes_new_evidence_and_refuses_overwrite(tmp_path, module_name):
    import subprocess
    import sys
    from pathlib import Path
    from experiments.artifacts import recheck_results_csv
    command = [sys.executable, str(Path('experiments') / (module_name + '.py')),
               '--output-dir', str(tmp_path)]
    first = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0, first.stdout + first.stderr
    path = tmp_path / (module_name + '.csv')
    assert recheck_results_csv(path)['validated_schedules'] == 7
    original = path.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert second.returncode != 0
    assert path.read_bytes() == original


def test_dynamic_snapshot_keeps_declared_machine_index_base(tmp_path):
    from pathlib import Path
    from src.research.batch import run_protocol
    root = Path(__file__).resolve().parents[1]
    protocol = tmp_path / 'protocol.json'
    protocol.write_text(json.dumps({
        'schema_version': 1, 'protocol_id': 'index-base-check', 'phase': 'Phase 2A',
        'instances': [{'id': 'mk06', 'path': 'instances/fjsplib/Brandimarte1993/mk06.fjs'}],
        'event_types': ['processing_time_change'], 'rules': ['fifo'], 'seeds': [42],
        'timing_repetitions': 1}), encoding='utf-8')
    result = run_protocol(protocol, tmp_path / 'batch', root, plots=False)
    assert result['status'] == 'COMPLETED'
    assert result['passed_runs'] == 1
