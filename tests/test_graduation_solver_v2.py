from dataclasses import replace

import pytest

from src.graduation import check_parallel_maintenance_feasibility, calculate_total_tardiness
from src.graduation import solver_v2 as module
from src.graduation.solver import GraduationSolverError, solve_parallel_maintenance
from tests.graduation_helpers import one_machine, two_machines


@pytest.mark.parametrize('builder,mode,want', [(one_machine, 'fixed', 4), (one_machine, 'joint', 0),
                                              (two_machines, 'fixed', 6), (two_machines, 'joint', 0)])
def test_v2_matches_hand_derived_optimum_and_original_solver(builder, mode, want):
    data, _ = builder()
    result = module.solve_parallel_maintenance_v2(data, mode=mode)
    original = solve_parallel_maintenance(data, mode=mode)
    assert check_parallel_maintenance_feasibility(result, data, mode=mode) == (True, [])
    assert result.solver_status == 'OPTIMAL'
    assert calculate_total_tardiness(data, result) == result.total_tardiness == want
    assert result.solver_objective_value == result.solver_objective_bound == want
    assert result.solver_gap == 0
    assert result.records == original.records
    assert result.maintenance_records == original.maintenance_records


def test_metric_fields_match_the_backend_definition():
    from src.ai_workflow.graduation_backend import METRICS
    assert module.METRICS == METRICS


@pytest.mark.parametrize('status,objective,bound,total,ok', [
    ('FEASIBLE', 88.0, 0.0, 86, True),     # exp_031 request 167
    ('FEASIBLE', 86.0, 0.0, 86, True),
    ('FEASIBLE', 86.0, 86.0, 86, True),
    ('OPTIMAL', 86.0, 86.0, 86, True),
    ('OPTIMAL', 88.0, 86.0, 86, False),
    ('OPTIMAL', 88.0, 88.0, 86, False),
    ('FEASIBLE', 85.0, 0.0, 86, False),    # claims better than the plan
    ('FEASIBLE', 88.0, 87.0, 86, False),   # bound above the plan
    ('FEASIBLE', 88.0, -1.0, 86, False),
    ('FEASIBLE', 88.5, 0.0, 86, False),
    ('FEASIBLE', 88.0, 0.5, 86, False),
    ('FEASIBLE', float('nan'), 0.0, 86, False),
    ('FEASIBLE', float('inf'), 0.0, 86, False),
    ('FEASIBLE', 88.0, 0.0, 86.0, False),
    ('FEASIBLE', 88.0, 0.0, True, False),
    ('UNKNOWN', 88.0, 0.0, 86, False),
])
def test_objective_metadata_rule(status, objective, bound, total, ok):
    if ok:
        module.check_objective_metadata(status, objective, bound, total)
    else:
        with pytest.raises(GraduationSolverError):
            module.check_objective_metadata(status, objective, bound, total)


@pytest.mark.parametrize('status,objective_shift,bound,accepted', [
    ('FEASIBLE', 2, 0.0, True),
    ('FEASIBLE', 0, 0.0, True),
    ('FEASIBLE', -1, 0.0, False),
    ('FEASIBLE', 0.5, 0.0, False),
    ('FEASIBLE', 2, 5.0, False),
    ('OPTIMAL', 2, None, False),
])
def test_solver_reports_exact_plan_tardiness_not_objective(monkeypatch, status, objective_shift, bound, accepted):
    real_solver = module.cp_model.CpSolver

    class Proxy:
        def __init__(self): self.delegate = real_solver()
        def __getattr__(self, name): return getattr(self.delegate, name)
        def Solve(self, model):
            self.delegate.Solve(model)
            return getattr(module.cp_model, status)
        def StatusName(self, value): return status
        def ObjectiveValue(self): return self.delegate.ObjectiveValue() + objective_shift
        def BestObjectiveBound(self):
            return self.delegate.BestObjectiveBound() if bound is None else bound

    monkeypatch.setattr(module.cp_model, 'CpSolver', Proxy)
    data, _ = one_machine()
    if not accepted:
        with pytest.raises(GraduationSolverError):
            module.solve_parallel_maintenance_v2(data, mode='fixed')
        return
    result = module.solve_parallel_maintenance_v2(data, mode='fixed')
    assert check_parallel_maintenance_feasibility(result, data, mode='fixed') == (True, [])
    assert result.total_tardiness == calculate_total_tardiness(data, result) == 4
    assert result.solver_objective_value == 4 + objective_shift
    assert result.solver_gap == (4 - bound) / 4
    assert module.checked_metrics_v2(data, result, 'fixed')['total_tardiness'] == 4


def test_checker_rejection_is_never_returned(monkeypatch):
    from src.graduation import MaintenanceViolation
    monkeypatch.setattr(module, 'check_parallel_maintenance_feasibility',
                        lambda *a, **kw: (False, [MaintenanceViolation('DENIED', 'refused')]))
    data, _ = one_machine()
    with pytest.raises(GraduationSolverError, match='rejected'):
        module.solve_parallel_maintenance_v2(data, mode='joint')


@pytest.mark.parametrize('change', ['gap', 'tardiness', 'optimal_objective', 'overlap', 'wall_time'])
def test_saved_result_recheck_rejects_tampering(change):
    data, _ = one_machine()
    result = module.solve_parallel_maintenance_v2(data, mode='fixed')
    if change == 'gap': result.solver_gap = 0.5
    if change == 'tardiness': result.total_tardiness += 1
    if change == 'optimal_objective': result.solver_objective_value += 1
    if change == 'overlap': result.maintenance_records[0] = replace(result.maintenance_records[0], start=1, end=3)
    if change == 'wall_time': result.solver_wall_time = -1.0
    with pytest.raises(ValueError):
        module.checked_metrics_v2(data, result, 'fixed')


@pytest.mark.parametrize('kwargs', [
    {'mode': 'wrong'}, {'time_limit': 0}, {'time_limit': float('nan')}, {'time_limit': True},
    {'num_workers': 0}, {'num_workers': 65}, {'seed': -1}, {'seed': 2**31},
    {'max_deterministic_time': 0}, {'max_deterministic_time': float('inf')},
    {'max_deterministic_time': True}, {'max_deterministic_time': '1'},
])
def test_invalid_configuration_is_rejected_before_search(kwargs):
    data, _ = one_machine()
    with pytest.raises(ValueError):
        module.solve_parallel_maintenance_v2(data, **({'mode': 'joint'} | kwargs))


def test_fixed_mode_requires_prespecified_maintenance():
    data, _ = one_machine(fixed_start=None)
    with pytest.raises(ValueError):
        module.solve_parallel_maintenance_v2(data, mode='fixed')


def test_deterministic_time_limit_repeats_the_same_feasible_plan():
    from src.graduation.reference_main_protocol import build_main_cases
    from src.graduation.reference_main_results import _data
    case = next(c for c in build_main_cases() if c['case_id'] == 'g3a-main-n24-m2-a10-b25-t75-s404-midpoint')
    data = _data(case)
    runs = [module.solve_parallel_maintenance_v2(data, mode='joint', time_limit=60.0,
                                                 max_deterministic_time=0.05) for _ in range(2)]
    assert runs[0].records == runs[1].records
    assert runs[0].maintenance_records == runs[1].maintenance_records
    assert runs[0].total_tardiness == runs[1].total_tardiness
    assert runs[0].solver_objective_value == runs[1].solver_objective_value
    assert runs[0].solver_wall_time < 60.0


def test_exp_034_smoke_on_one_failed_request(tmp_path, monkeypatch):
    import csv
    import json
    from experiments import exp_034_graduation_solver_v2_check as experiment
    monkeypatch.setattr(experiment, 'FAILED_REQUESTS', experiment.FAILED_REQUESTS[:1])
    monkeypatch.setattr(experiment, 'DETERMINISTIC_SETTINGS',
                        experiment.DETERMINISTIC_SETTINGS | {'max_deterministic_time': 0.05})
    manifest = experiment.run_experiment(tmp_path / 'out')
    assert manifest['status'] == 'PASSED' and all(manifest['checks'].values())
    with open(tmp_path / 'out' / 'rows.csv', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == manifest['rows'] == 4 + 24
    v2 = [r for r in rows if r['part'] in ('A', 'B') and r['solver'] == 'v2']
    assert all(r['status'] == 'ACCEPTED' and int(r['total_tardiness']) <= float(r['objective']) for r in v2)
    assert json.loads((tmp_path / 'out' / 'plans.json').read_text(encoding='utf-8'))
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path / 'out')
