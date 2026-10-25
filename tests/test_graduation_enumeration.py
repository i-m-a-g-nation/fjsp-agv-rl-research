from copy import deepcopy
import random

import pytest

from src.graduation import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from tests.graduation_helpers import one_machine, two_machines


@pytest.mark.parametrize('builder,mode,want', [(one_machine, 'fixed', 4), (one_machine, 'joint', 0),
                                              (two_machines, 'fixed', 6), (two_machines, 'joint', 0)])
def test_independent_oracle_matches_hand_derived_values_without_cpsat(monkeypatch, builder, mode, want):
    from src.graduation.enumeration import enumerate_parallel_maintenance
    from src.graduation import solver
    def forbidden(*a, **kw): pytest.fail('Enumeration must not call CP-SAT')
    monkeypatch.setattr(solver.cp_model, 'CpSolver', forbidden)
    data, _ = builder()
    result = enumerate_parallel_maintenance(data, mode=mode)
    assert result.total_tardiness == result.solver_objective_bound == want
    assert result.solver_status == 'OPTIMAL' and result.solver_gap == 0


@pytest.mark.parametrize('seed', range(12))
def test_seeded_variable_instances_match_exact_oracle_for_both_domains(seed):
    from src.graduation.enumeration import enumerate_parallel_maintenance
    from src.graduation import solve_parallel_maintenance, check_parallel_maintenance_feasibility
    rng = random.Random(seed)
    machines = 1 + seed % 2
    tasks = tuple(ProductionTask(j, rng.randint(1, 3), rng.randint(0, 9)) for j in range(1 + seed % 3))
    requirements = []
    for machine in range(machines):
        start, duration, slack = rng.randint(0, 3), rng.randint(1, 2), rng.randint(0, 2)
        requirements.append(MaintenanceRequirement(machine, duration, start, start + duration + slack,
                                                   start + rng.randint(0, slack)))
    data = ParallelMaintenanceInstance(tasks, machines, tuple(requirements))
    before = deepcopy(data)
    totals = {}
    for mode in ('fixed', 'joint'):
        actual = solve_parallel_maintenance(data, mode=mode)
        reference = enumerate_parallel_maintenance(data, mode=mode)
        assert actual.solver_status == reference.solver_status == 'OPTIMAL'
        assert actual.total_tardiness == reference.total_tardiness
        assert check_parallel_maintenance_feasibility(reference, data, mode=mode) == (True, [])
        totals[mode] = reference.total_tardiness
    assert totals['joint'] <= totals['fixed']
    assert data == before


def test_budget_exhaustion_does_not_return_best_prefix_or_claim_optimality():
    from src.graduation.enumeration import enumerate_parallel_maintenance, EnumerationLimitError
    data, _ = two_machines()
    with pytest.raises(EnumerationLimitError): enumerate_parallel_maintenance(data, mode='joint', max_states=1)


def test_wide_maintenance_windows_are_rejected_before_cartesian_pools_are_materialized(monkeypatch):
    from src.graduation import enumeration as module
    data = ParallelMaintenanceInstance((ProductionTask(0, 1, 1),), 1,
                                      (MaintenanceRequirement(0, 1, 0, 1000000, 0),))
    def forbidden(*a, **kw): pytest.fail('Budget guard must run before product materializes its pools')
    monkeypatch.setattr(module, 'product', forbidden)
    with pytest.raises(module.EnumerationLimitError):
        module.enumerate_parallel_maintenance(data, mode='joint', max_states=1)


@pytest.mark.parametrize('limit', [0, True, 1.0, 200001])
def test_enumeration_rejects_invalid_or_unbounded_budgets(limit):
    from src.graduation.enumeration import enumerate_parallel_maintenance
    data, _ = one_machine()
    with pytest.raises(ValueError): enumerate_parallel_maintenance(data, mode='joint', max_states=limit)


def test_oracle_rejects_unsupported_size_and_fixed_mode_without_start():
    from src.graduation.enumeration import enumerate_parallel_maintenance, EnumerationLimitError
    data, _ = one_machine(fixed_start=None)
    with pytest.raises(ValueError): enumerate_parallel_maintenance(data, mode='fixed')
    with pytest.raises(ValueError): enumerate_parallel_maintenance(data, mode='other')
    big = ParallelMaintenanceInstance(tuple(ProductionTask(j, 1, 1) for j in range(6)), 1,
                                      (MaintenanceRequirement(0, 1, 0, 2, 0),))
    with pytest.raises(EnumerationLimitError): enumerate_parallel_maintenance(big, mode='joint')
