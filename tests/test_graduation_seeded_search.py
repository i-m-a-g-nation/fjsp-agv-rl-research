import pytest

from src.graduation.dispatch_rules import solve_dispatch_rule
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metaheuristics import solve_metaheuristic
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data
from src.graduation.seeded_search import decoded_value, plan_to_sequence, solve_seeded_iga


def _data_for(n, m):
    case = next(c for c in build_main_cases()
                if c['factors']['num_tasks'] == n and c['factors']['num_machines'] == m)
    return _data(case)


def test_without_seeds_it_is_exactly_the_exp_040_iga():
    data = _data_for(24, 4)
    plain = solve_metaheuristic(data, mode='joint', algorithm='IGA', evaluations=500, seed=2)
    seeded = solve_seeded_iga(data, mode='joint', seeds=[], evaluations=500, seed=2)
    assert seeded.sequence == plain.sequence and seeded.evaluations == plain.evaluations


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
def test_rule_plan_round_trip_and_seed_is_never_lost(mode):
    data = _data_for(24, 2)
    rule = solve_dispatch_rule(data, mode=mode, rule='MDD')
    sequence = plan_to_sequence(rule, data)
    value = decoded_value(data, mode, sequence)
    assert value >= 0
    outcome = solve_seeded_iga(data, mode=mode, seeds=[sequence], evaluations=300, seed=0)
    assert outcome.result.total_tardiness <= value
    assert check_parallel_maintenance_feasibility(outcome.result, data, mode=mode)[0]
    assert outcome.evaluations <= 300


def test_rejects_bad_seeds_and_arguments():
    data = _data_for(8, 2)
    with pytest.raises(ValueError):
        solve_seeded_iga(data, mode='joint', seeds=[[0, 1, 2]])
    with pytest.raises(ValueError):
        solve_seeded_iga(data, mode='joint', seeds=[], evaluations=0)
    rule = solve_dispatch_rule(data, mode='joint', rule='EDD')
    rule.maintenance_records = rule.maintenance_records[:1]
    with pytest.raises(ValueError):
        plan_to_sequence(rule, data)
