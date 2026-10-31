import pytest

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metaheuristics import (
    ALGORITHMS, MetaheuristicError, _order_crossover, _Problem, solve_metaheuristic,
)
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data


def _single_machine_example(fixed_start=0):
    tasks = (ProductionTask(0, 2, 2), ProductionTask(1, 2, 4))
    return ParallelMaintenanceInstance(tasks, 1, (MaintenanceRequirement(0, 2, 0, 6, fixed_start),))


def _case(n, m):
    return next(c for c in build_main_cases()
                if c['factors']['num_tasks'] == n and c['factors']['num_machines'] == m)


@pytest.mark.parametrize('algorithm', ALGORITHMS)
def test_hand_example_reaches_known_optima(algorithm):
    data = _single_machine_example()
    assert solve_metaheuristic(data, mode='fixed', algorithm=algorithm, evaluations=200).result.total_tardiness == 4
    assert solve_metaheuristic(data, mode='joint', algorithm=algorithm, evaluations=200).result.total_tardiness == 0


@pytest.mark.parametrize('algorithm', ALGORITHMS)
@pytest.mark.parametrize('mode', ['fixed', 'joint'])
@pytest.mark.parametrize('size', [(8, 2), (24, 4)])
def test_every_returned_plan_passes_g1(algorithm, mode, size):
    data = _data(_case(*size))
    outcome = solve_metaheuristic(data, mode=mode, algorithm=algorithm, evaluations=300, seed=3)
    accepted, issues = check_parallel_maintenance_feasibility(outcome.result, data, mode=mode)
    assert accepted, issues
    assert 1 <= outcome.best_evaluation <= outcome.evaluations <= 300
    if mode == 'fixed':
        starts = {r.machine_id: r.start for r in outcome.result.maintenance_records}
        assert starts == {item.machine_id: item.fixed_start for item in data.maintenance}


def test_same_seed_is_deterministic_and_seeds_differ_in_trace():
    data = _data(_case(24, 2))
    a = solve_metaheuristic(data, mode='joint', algorithm='GA', evaluations=400, seed=1)
    b = solve_metaheuristic(data, mode='joint', algorithm='GA', evaluations=400, seed=1)
    c = solve_metaheuristic(data, mode='joint', algorithm='GA', evaluations=400, seed=2)
    assert a.sequence == b.sequence and a.result.total_tardiness == b.result.total_tardiness
    assert a.sequence != c.sequence


def test_tiny_budget_and_large_instance_without_size_cap():
    data = _data(_case(8, 2))
    assert solve_metaheuristic(data, mode='joint', algorithm='IGA', evaluations=1).evaluations == 1
    tasks = tuple(ProductionTask(j, 1 + j % 7, 5 + 3 * j) for j in range(60))
    maintenance = tuple(MaintenanceRequirement(i, 4, 10, 40, 20) for i in range(5))
    big = ParallelMaintenanceInstance(tasks, 5, maintenance)
    for mode in ('fixed', 'joint'):
        outcome = solve_metaheuristic(big, mode=mode, algorithm='SA', evaluations=200)
        assert check_parallel_maintenance_feasibility(outcome.result, big, mode=mode)[0]


def test_decoder_forces_maintenance_before_a_job_that_would_overrun():
    data = ParallelMaintenanceInstance((ProductionTask(0, 5, 0),), 1, (MaintenanceRequirement(0, 2, 0, 4, 1),))
    for mode, start in (('fixed', 1), ('joint', 0)):
        total, jobs, maintenance = _Problem(data, mode).decode([0, 1], plan=True)
        assert maintenance == [(0, start)] and jobs == [(0, 0, start + 2)] and total == start + 7


def test_order_crossover_returns_a_permutation():
    import random
    rng = random.Random(0)
    for _ in range(50):
        a, b = rng.sample(range(12), 12), rng.sample(range(12), 12)
        assert sorted(_order_crossover(a, b, rng)) == list(range(12))


def test_rejects_bad_arguments():
    data = _single_machine_example()
    with pytest.raises(ValueError):
        solve_metaheuristic(data, mode='joint', algorithm='PSO')
    with pytest.raises(ValueError):
        solve_metaheuristic(data, mode='joint', algorithm='GA', evaluations=0)
    with pytest.raises(ValueError):
        solve_metaheuristic(data, mode='other', algorithm='GA')
    with pytest.raises(ValueError):
        solve_metaheuristic(_single_machine_example(None), mode='fixed', algorithm='GA')


def test_decoder_mismatch_is_never_returned(monkeypatch):
    data = _single_machine_example()
    original = _Problem.decode

    def corrupt(self, sequence, plan=False):
        value = original(self, sequence, plan)
        return (value[0] + 1, *value[1:]) if plan else value

    monkeypatch.setattr(_Problem, 'decode', corrupt)
    with pytest.raises(MetaheuristicError):
        solve_metaheuristic(data, mode='joint', algorithm='SA', evaluations=50)
