from types import SimpleNamespace

import pytest

from src.graduation import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from tests.graduation_helpers import one_machine, two_machines


@pytest.mark.parametrize('builder,mode,want', [(one_machine, 'fixed', 4), (one_machine, 'joint', 0),
                                              (two_machines, 'fixed', 6), (two_machines, 'joint', 0)])
def test_solver_minimizes_hand_derived_tardiness_and_retains_objective_metadata(builder, mode, want):
    from src.graduation.solver import solve_parallel_maintenance
    from src.graduation import check_parallel_maintenance_feasibility, calculate_total_tardiness
    data, _ = builder()
    result = solve_parallel_maintenance(data, mode=mode)
    assert check_parallel_maintenance_feasibility(result, data, mode=mode) == (True, [])
    assert result.solver_status == 'OPTIMAL'
    assert calculate_total_tardiness(data, result) == result.total_tardiness == want
    assert result.solver_objective_value == result.solver_objective_bound == want
    assert result.solver_gap == 0 and result.solver_wall_time >= 0


def test_late_mandatory_maintenance_does_not_change_production_makespan_or_zero_objective():
    from src.graduation.solver import solve_parallel_maintenance
    data = ParallelMaintenanceInstance((ProductionTask(0, 1, 1),), 1, (MaintenanceRequirement(0, 1, 3, 4, 3),))
    result = solve_parallel_maintenance(data, mode='joint')
    assert result.total_tardiness == 0 and result.makespan == 1
    assert [(r.start, r.end) for r in result.maintenance_records] == [(3, 4)]
    assert result.solver_objective_bound == 0 and result.solver_gap == 0


def test_tight_windows_force_maintenance_on_idle_machine_too():
    from src.graduation.solver import solve_parallel_maintenance
    data = ParallelMaintenanceInstance((ProductionTask(0, 2, 2),), 2,
        tuple(MaintenanceRequirement(m, 2, 0, 2, 0) for m in range(2)))
    result = solve_parallel_maintenance(data, mode='joint')
    assert result.total_tardiness == 2 and result.makespan == 4
    assert sorted((r.machine_id, r.start, r.end) for r in result.maintenance_records) == [(0, 0, 2), (1, 0, 2)]


@pytest.mark.parametrize('kwargs', [
    {'mode': 'wrong'}, {'time_limit': 0}, {'time_limit': float('nan')}, {'time_limit': float('inf')},
    {'time_limit': True}, {'num_workers': 0}, {'num_workers': 65}, {'num_workers': 1.0},
    {'num_workers': True}, {'seed': -1}, {'seed': True}, {'seed': 2**31},
])
def test_invalid_configuration_is_rejected_before_search(kwargs):
    from src.graduation.solver import solve_parallel_maintenance
    data, _ = one_machine()
    with pytest.raises(ValueError):
        solve_parallel_maintenance(data, **({'mode': 'joint'} | kwargs))


def test_fixed_mode_requires_prespecified_maintenance_and_numeric_domain_is_guarded():
    from src.graduation.solver import solve_parallel_maintenance
    data, _ = one_machine(fixed_start=None)
    with pytest.raises(ValueError): solve_parallel_maintenance(data, mode='fixed')
    huge = ParallelMaintenanceInstance((ProductionTask(0, 2**62, 0),), 1,
                                       (MaintenanceRequirement(0, 1, 0, 1, 0),))
    with pytest.raises(ValueError): solve_parallel_maintenance(huge, mode='joint')


@pytest.mark.parametrize('name', ['UNKNOWN', 'INFEASIBLE', 'MODEL_INVALID'])
def test_status_without_solution_never_attempts_extraction(monkeypatch, name):
    from src.graduation import solver as module
    class NoSolution:
        parameters = SimpleNamespace()
        def Solve(self, model): return getattr(module.cp_model, name)
        def StatusName(self, status): return name
        def Value(self, value): pytest.fail('No-solution status must not extract a schedule')
    monkeypatch.setattr(module.cp_model, 'CpSolver', NoSolution)
    data, _ = one_machine()
    with pytest.raises(module.GraduationSolverError, match=name):
        module.solve_parallel_maintenance(data, mode='joint')


@pytest.mark.parametrize('fault', ['feasible', 'objective', 'checker'])
def test_feasible_is_not_promoted_and_extraction_requires_independent_acceptance(monkeypatch, fault):
    from src.graduation import solver as module
    from src.graduation import MaintenanceViolation
    real_solver = module.cp_model.CpSolver
    class Proxy:
        def __init__(self): self.delegate = real_solver()
        def __getattr__(self, name): return getattr(self.delegate, name)
        def Solve(self, model):
            status = self.delegate.Solve(model)
            return module.cp_model.FEASIBLE if fault == 'feasible' else status
        def ObjectiveValue(self): return self.delegate.ObjectiveValue() + (1 if fault == 'objective' else 0)
    monkeypatch.setattr(module.cp_model, 'CpSolver', Proxy)
    if fault == 'checker':
        monkeypatch.setattr(module, 'check_parallel_maintenance_feasibility',
                            lambda *a, **kw: (False, [MaintenanceViolation('DENIED', 'refused')]))
    data, _ = one_machine()
    if fault == 'feasible':
        result = module.solve_parallel_maintenance(data, mode='fixed')
        assert result.solver_status == 'FEASIBLE' and result.total_tardiness == 4
    else:
        with pytest.raises(module.GraduationSolverError): module.solve_parallel_maintenance(data, mode='joint')
