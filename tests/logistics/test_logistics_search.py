"""L1 metaheuristics: checker-accepted, never worse than the rules they start from, reproducible, on budget."""

from pathlib import Path

import pytest

from fjsp_lab.fjsp import create_toy_instance, load_project_benchmark_file
from fjsp_lab.logistics import LogisticsInstance, check_logistics_feasibility
from fjsp_lab.logistics.cpsat import solve_cpsat
from fjsp_lab.logistics.metaheuristics import Codec, solve_ga, solve_sa
from fjsp_lab.logistics.rules import RULES, solve_rule

MK01 = Path(__file__).resolve().parents[2] / 'instances' / 'fjsplib' / 'Brandimarte1993' / 'mk01.fjs'


def layout(m, scale=3):
    return [[0 if a == b else scale * (1 + abs(a - b)) for b in range(m + 1)] for a in range(m + 1)]


def instance(production, buffer=None, blocking=True, back=False):
    return LogisticsInstance.create(production, layout(production.num_machines), num_vehicles=2,
                                    buffer_capacity=buffer, blocking=blocking, return_to_lu=back)


@pytest.mark.parametrize('solver', [solve_ga, solve_sa])
def test_search_is_accepted_on_budget_reproducible_and_not_worse_than_rules(solver):
    production = load_project_benchmark_file(MK01)
    for buffer, blocking, back in ((None, False, False), (1, True, True), (0, True, False)):
        data = instance(production, buffer, blocking, back)
        outcome = solver(data, evaluations=60, seed=3)
        assert check_logistics_feasibility(outcome.schedule, data) == (True, [])
        assert outcome.evaluations == 60
        rules = min(solve_rule(data, rule, avoid_deadlock=True).makespan for rule in RULES[:4])
        assert outcome.schedule.makespan <= rules
        assert [t for _, t in outcome.trace] == sorted((t for _, t in outcome.trace), reverse=True)
        again = solver(data, evaluations=60, seed=3)
        assert again.schedule == outcome.schedule and again.trace == outcome.trace


def test_search_never_beats_the_proven_optimum():
    production = create_toy_instance()
    for buffer in (None, 0):
        data = instance(production, buffer)
        optimum = solve_cpsat(data, time_limit=30)
        assert optimum.solver_status == 'OPTIMAL'
        for solver in (solve_ga, solve_sa):
            assert solver(data, evaluations=300, seed=0).schedule.makespan >= optimum.makespan


def test_codec_reproduces_a_schedule_without_losing_quality():
    production = load_project_benchmark_file(MK01)
    data = instance(production, None, blocking=False)
    codec = Codec(data)
    for rule in RULES[:4]:
        schedule = solve_rule(data, rule)
        decoded, fallback = codec.decode(codec.from_schedule(schedule))
        assert not fallback and decoded.makespan <= schedule.makespan
        assert check_logistics_feasibility(decoded, data)[0] is True


def test_time_limited_annealing_stops_on_time_and_is_checked():
    import time
    production = load_project_benchmark_file(MK01)
    data = instance(production, None, blocking=False)
    started = time.perf_counter()
    outcome = solve_sa(data, evaluations=10 ** 9, seed=0, time_limit=0.5)
    assert time.perf_counter() - started < 5.0
    assert 4 < outcome.evaluations < 10 ** 9
    assert check_logistics_feasibility(outcome.schedule, data) == (True, [])
    with pytest.raises(ValueError):
        solve_sa(data, evaluations=10, time_limit=0)
