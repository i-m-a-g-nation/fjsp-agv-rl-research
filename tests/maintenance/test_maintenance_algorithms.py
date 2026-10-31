"""Every maintenance algorithm returns a checker-accepted plan; exact methods agree."""

import pytest

from fjsp_lab.maintenance import check_parallel_maintenance_feasibility
from fjsp_lab.maintenance.cpsat import CpSatError, check_objective_metadata, solve_cpsat
from fjsp_lab.maintenance.enumeration import EnumerationLimitError, enumerate_parallel_maintenance
from fjsp_lab.maintenance.env import (
    MAINTENANCE_OFFSET, ParallelMaintenanceEnv, actions_for_plan,
)
from fjsp_lab.maintenance.generator import build_instance
from fjsp_lab.maintenance.metaheuristics import (
    ALGORITHMS, decoded_value, plan_to_sequence, solve_metaheuristic,
)
from fjsp_lab.maintenance.rules import RULE_PORTFOLIO, solve_dispatch_rule

MODES = ('fixed', 'joint')
TINY = [build_instance(3, 2, a, b, t, s) for a in (10, 30) for b in (25, 75) for t in (75, 125) for s in (1, 2)]


def accepted(result, data, mode):
    ok, violations = check_parallel_maintenance_feasibility(result, data, mode=mode)
    assert ok is True, violations
    return result.total_tardiness


@pytest.mark.parametrize('mode', MODES)
def test_cpsat_matches_independent_enumeration_on_tiny_instances(mode):
    for data in TINY:
        exact = enumerate_parallel_maintenance(data, mode=mode)
        solved = solve_cpsat(data, mode=mode, time_limit=10)
        assert solved.solver_status == 'OPTIMAL'
        assert accepted(solved, data, mode) == accepted(exact, data, mode)


def test_joint_optimum_never_exceeds_fixed_optimum(small):
    fixed = solve_cpsat(small, mode='fixed', time_limit=10)
    joint = solve_cpsat(small, mode='joint', time_limit=10)
    assert fixed.solver_status == joint.solver_status == 'OPTIMAL'
    assert accepted(joint, small, 'joint') <= accepted(fixed, small, 'fixed')


def test_cpsat_objective_acceptance_rule():
    check_objective_metadata('FEASIBLE', 88.0, 0.0, 86)            # objective is only an upper bound
    for args in (('OPTIMAL', 88.0, 86.0, 86), ('FEASIBLE', 85.0, 0.0, 86), ('FEASIBLE', 88.5, 0.0, 86),
                 ('UNKNOWN', 1.0, 0.0, 1), ('FEASIBLE', 88.0, 87.0, 86)):
        with pytest.raises(CpSatError):
            check_objective_metadata(*args)


def test_enumeration_refuses_instances_it_cannot_certify(small):
    with pytest.raises(EnumerationLimitError):
        enumerate_parallel_maintenance(small, mode='joint')


@pytest.mark.parametrize('mode', MODES)
def test_dispatch_rules_return_accepted_plans(mode, cases):
    for case in cases[::8]:
        for rule, k in RULE_PORTFOLIO:
            accepted(solve_dispatch_rule(case.data, mode=mode, rule=rule, atc_k=k), case.data, mode)
    with pytest.raises(ValueError):
        solve_dispatch_rule(cases[0].data, mode=mode, rule='LPT')


@pytest.mark.parametrize('algorithm', ALGORITHMS)
@pytest.mark.parametrize('mode', MODES)
def test_metaheuristics_respect_budget_and_return_accepted_plans(algorithm, mode, large):
    outcome = solve_metaheuristic(large, mode=mode, algorithm=algorithm, evaluations=600, seed=3)
    assert outcome.evaluations <= 600 and 1 <= outcome.best_evaluation <= outcome.evaluations
    assert accepted(outcome.result, large, mode) == decoded_value(large, mode, list(outcome.sequence))
    again = solve_metaheuristic(large, mode=mode, algorithm=algorithm, evaluations=600, seed=3)
    assert again.sequence == outcome.sequence


def test_iga_is_never_worse_than_its_heuristic_seeds_and_honours_initial_sequences(large):
    for mode in MODES:
        mdd = solve_dispatch_rule(large, mode=mode, rule='MDD')
        start = plan_to_sequence(mdd, large)
        outcome = solve_metaheuristic(large, mode=mode, algorithm='IGA', evaluations=500, initial_sequences=[start])
        assert accepted(outcome.result, large, mode) <= decoded_value(large, mode, start)
    with pytest.raises(ValueError):
        solve_metaheuristic(large, mode='joint', algorithm='IGA', initial_sequences=[[0, 0, 1]])
    with pytest.raises(ValueError):
        solve_metaheuristic(large, mode='joint', algorithm='SA', initial_sequences=[start])


def test_environment_masks_and_terminal_plan(small):
    env = ParallelMaintenanceEnv(small, mode='fixed')
    legal = env.legal_actions()
    assert legal == sorted(legal) and env.action_masks().count(True) == len(legal)
    with pytest.raises(ValueError):
        env.step(99 if 99 not in legal else -1)
    total, steps = 0.0, 0
    while not env.done:
        legal = env.legal_actions()
        step = env.step(legal[-1] if legal[-1] >= MAINTENANCE_OFFSET else legal[0])
        total, steps = total + step.reward, steps + 1
    assert steps == 8 + 2 and step.terminated
    assert accepted(step.result, small, 'fixed') == round(-total * 100)
    with pytest.raises(RuntimeError):
        env.step(legal[0])


def test_environment_rejects_out_of_range_sizes():
    with pytest.raises(ValueError, match='at most'):
        ParallelMaintenanceEnv(build_instance(25, 2, 10, 25, 75, 1), mode='joint')


@pytest.mark.parametrize('mode', MODES)
def test_metaheuristic_plans_replay_through_the_environment(mode, large):
    outcome = solve_metaheuristic(large, mode=mode, algorithm='IGA', evaluations=300)
    actions = actions_for_plan(outcome.result, large, mode)
    assert len(actions) == 24 + 4
    tampered = outcome.result
    tampered.total_tardiness += 1
    with pytest.raises(ValueError):
        actions_for_plan(tampered, large, mode)
