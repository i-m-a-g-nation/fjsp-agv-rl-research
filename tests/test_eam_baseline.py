import pytest

from src.data.instance import FJSPInstance
from src.scheduling.feasibility import check_feasibility


@pytest.mark.parametrize('options', [[(0, 9), (1, 2)], [(1, 2), (0, 9)]])
def test_eam_ties_use_machine_id_and_do_not_alias_earliest_finish(options):
    from src.solvers.dispatching import dispatch_eam_solve, dispatch_eft_solve
    instance = FJSPInstance.from_jobs_array([[options]], num_machines=2)
    eam, eft = dispatch_eam_solve(instance), dispatch_eft_solve(instance)
    assert (eam.records[0].machine_id, eam.makespan) == (0, 9)
    assert (eft.records[0].machine_id, eft.makespan) == (1, 2)
    assert check_feasibility(eam)[0]


def test_eam_chooses_the_earlier_start_even_when_that_machine_finishes_later():
    from src.solvers.dispatching import dispatch_eam_solve
    instance = FJSPInstance.from_jobs_array([[[ (0, 4) ]], [[(0, 1), (1, 8)]]], num_machines=2)
    result = dispatch_eam_solve(instance)
    records = {(r.job_id, r.op_id): r for r in result.records}
    assert (records[(0, 0)].machine_id, records[(0, 0)].start, records[(0, 0)].end) == (0, 0, 4)
    assert (records[(1, 0)].machine_id, records[(1, 0)].start, records[(1, 0)].end) == (1, 0, 8)
    assert check_feasibility(result)[0]


def test_eam_ties_on_feasible_start_after_precedence_use_machine_id():
    from src.solvers.dispatching import dispatch_eam_solve
    instance = FJSPInstance.from_jobs_array([[[(0, 6)], [(1, 3), (0, 1)]]], num_machines=2)
    result = dispatch_eam_solve(instance)
    record = next(r for r in result.records if r.op_id == 1)
    assert (record.machine_id, record.start, record.end) == (0, 6, 7)
    assert check_feasibility(result)[0]


def test_eam_public_facades_return_uniform_legal_schedules():
    from src.solvers import earliest_available_machine_solve
    from src.solvers.heuristics import dispatch_eam_solve
    from src.scheduling.encoding import ScheduleResult
    instance = FJSPInstance.from_jobs_array([[[(0, 3), (1, 1)]]], num_machines=2)
    for solve in (earliest_available_machine_solve, dispatch_eam_solve):
        result = solve(instance)
        assert isinstance(result, ScheduleResult) and result.instance == instance
        assert result.makespan == 3
        assert check_feasibility(result)[0]


@pytest.mark.parametrize('entry', ['batch', 'matrix'])
def test_benchmark_entry_runs_eam_without_substituting_eft(entry):
    """Omitting EAM, or registering EFT under its name, must fail this witness."""
    from experiments.common import run_solver_suite
    from experiments.exp_005_benchmark_batch import build_solver_specs
    from experiments.exp_010_heuristic_benchmark_matrix import build_heuristic_specs
    instance = FJSPInstance.from_jobs_array([[[(0, 9), (1, 2)]]], num_machines=2)
    specs = (build_solver_specs(include_cp_sat=False) if entry == 'batch' else
             [(s.run_label, s.solver_fn) for s in build_heuristic_specs([42])])
    runs = run_solver_suite([(name, lambda fn=fn: fn(instance)) for name, fn in specs],
                            expected_instance=instance)
    eam = [r for r in runs if r.algorithm == 'EarliestAvailableMachine']
    assert len(eam) == 1
    assert eam[0].feasible and eam[0].makespan == 9
    assert eam[0].result.records[0].machine_id == 0


@pytest.mark.parametrize(('module', 'label', 'count'), [
    ('exp_003_dispatching_rules', 'DispatchEAM', 1),
    ('exp_004_benchmark_smoke', 'EarliestAvailableMachine', 2),
])
def test_static_cli_archives_checked_eam_plans(tmp_path, module, label, count):
    import csv
    import subprocess
    import sys
    from experiments.artifacts import recheck_results_csv
    run = subprocess.run([sys.executable, 'experiments/' + module + '.py',
                          '--output-dir', str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    path = tmp_path / (module + '.csv')
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    eam = [r for r in rows if r['algorithm'] == label]
    assert len(eam) == count
    assert recheck_results_csv(path)['validated_schedules'] == len(rows)


def test_eam_benchmark_reaches_quality_report_with_hand_checked_gap(tmp_path):
    from experiments.exp_010_heuristic_benchmark_matrix import (
        build_heuristic_specs, run_heuristic_benchmark_matrix, write_heuristic_aggregates_csv)
    from experiments.exp_011_heuristic_quality_report import (
        BenchmarkReference, build_quality_rows, aggregate_family_quality)
    path = tmp_path / 'witness.fjs'
    path.write_text('1 2 2.0\n1 2 0 9 1 2\n', encoding='utf-8')
    _, aggregates, failures = run_heuristic_benchmark_matrix(
        [path], tmp_path, build_heuristic_specs([42]))
    assert not failures
    summary = tmp_path / 'summary.csv'
    write_heuristic_aggregates_csv(summary, aggregates)
    rows = build_quality_rows(summary, {'witness.fjs': BenchmarkReference('witness.fjs', 2, 2)})
    eam = [row for row in rows if row.family == 'EarliestAvailableMachine']
    assert len(eam) == 1
    assert eam[0].mean_gap_ratio == 3.5  # (9 - 2) / 2, not EFT's zero gap.
    assert any(row.family == 'EarliestAvailableMachine' for row in aggregate_family_quality(rows))
