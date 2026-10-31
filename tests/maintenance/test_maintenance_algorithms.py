"""Every maintenance algorithm returns a checker-accepted plan; exact methods agree."""

import random

import numpy as np
import pytest

from fjsp_lab.maintenance import check_parallel_maintenance_feasibility
from fjsp_lab.maintenance.cpsat import CpSatError, check_objective_metadata, solve_cpsat
from fjsp_lab.maintenance.enumeration import EnumerationLimitError, enumerate_parallel_maintenance
from fjsp_lab.maintenance.env import ParallelMaintenanceEnv, actions_for_plan
from fjsp_lab.maintenance.generator import build_instance, build_periodic_instance
from fjsp_lab.maintenance.metaheuristics import ALGORITHMS, decoded_value, plan_to_sequence, solve_metaheuristic
from fjsp_lab.maintenance.rules import RULE_PORTFOLIO, solve_dispatch_rule
from fjsp_lab.maintenance.sequence_env import SEQUENCE_FEATURE_COUNT, SequenceEnv, teacher_actions

MODES = ('fixed', 'joint')
FACTORS = [(a, b, t, s) for a in (10, 30) for b in (25, 75) for t in (75, 125) for s in (1, 2)]
TINY = [build_instance(3, 2, *f) for f in FACTORS]
TINY_PERIODIC = [build_periodic_instance(3, 2, (1, 2), min(a, 20), min(b, 50), t, s) for a, b, t, s in FACTORS]


def accepted(result, data, mode):
    ok, violations = check_parallel_maintenance_feasibility(result, data, mode=mode)
    assert ok is True, violations
    return result.total_tardiness


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('instances', [TINY, TINY_PERIODIC], ids=['one-window', 'periodic'])
def test_cpsat_matches_independent_enumeration_on_tiny_instances(mode, instances):
    for data in instances:
        exact = enumerate_parallel_maintenance(data, mode=mode)
        solved = solve_cpsat(data, mode=mode, time_limit=10)
        assert solved.solver_status == 'OPTIMAL'
        assert accepted(solved, data, mode) == accepted(exact, data, mode)


def test_joint_optimum_never_exceeds_fixed_optimum(small):
    fixed = solve_cpsat(small, mode='fixed', time_limit=10)
    joint = solve_cpsat(small, mode='joint', time_limit=10)
    assert fixed.solver_status == joint.solver_status == 'OPTIMAL'
    assert accepted(joint, small, 'joint') <= accepted(fixed, small, 'fixed')


def test_cpsat_returns_accepted_plans_on_periodic_instances(periodic):
    for mode in MODES:
        result = solve_cpsat(periodic, mode=mode, time_limit=2)
        accepted(result, periodic, mode)
        assert len(result.maintenance_records) == periodic.num_windows == 7


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
def test_dispatch_rules_return_accepted_plans(mode, cases, periodic, periodic_big):
    for data in [case.data for case in cases[::8]] + [periodic, periodic_big]:
        for rule, k in RULE_PORTFOLIO:
            accepted(solve_dispatch_rule(data, mode=mode, rule=rule, atc_k=k), data, mode)
    with pytest.raises(ValueError):
        solve_dispatch_rule(cases[0].data, mode=mode, rule='LPT')


@pytest.mark.parametrize('algorithm', ALGORITHMS)
@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('fixture', ['large', 'periodic'])
def test_metaheuristics_respect_budget_and_return_accepted_plans(algorithm, mode, fixture, request):
    data = request.getfixturevalue(fixture)
    outcome = solve_metaheuristic(data, mode=mode, algorithm=algorithm, evaluations=600, seed=3)
    assert outcome.evaluations <= 600 and 1 <= outcome.best_evaluation <= outcome.evaluations
    assert accepted(outcome.result, data, mode) == decoded_value(data, mode, list(outcome.sequence))
    again = solve_metaheuristic(data, mode=mode, algorithm=algorithm, evaluations=600, seed=3)
    assert again.sequence == outcome.sequence


@pytest.mark.parametrize('fixture', ['large', 'periodic'])
def test_iga_is_never_worse_than_its_initial_sequence(fixture, request):
    data = request.getfixturevalue(fixture)
    for mode in MODES:
        start = plan_to_sequence(solve_dispatch_rule(data, mode=mode, rule='MDD'), data)
        outcome = solve_metaheuristic(data, mode=mode, algorithm='IGA', evaluations=500, initial_sequences=[start])
        assert accepted(outcome.result, data, mode) <= decoded_value(data, mode, start)
    with pytest.raises(ValueError):
        solve_metaheuristic(data, mode='joint', algorithm='IGA', initial_sequences=[[0, 0, 1]])
    with pytest.raises(ValueError):
        solve_metaheuristic(data, mode='joint', algorithm='SA', initial_sequences=[start])


@pytest.mark.parametrize('fixture', ['small', 'periodic'])
def test_environment_steps_and_terminal_plan(fixture, request):
    data = request.getfixturevalue(fixture)
    env = ParallelMaintenanceEnv(data, mode='fixed')
    with pytest.raises(ValueError):
        env.step(env.maintenance_offset + data.num_machines)
    total, steps = 0.0, 0
    while not env.done:
        legal = env.legal_actions()
        assert legal == sorted(legal)
        step = env.step(legal[-1] if env.is_maintenance(legal[-1]) else legal[0])
        total, steps = total + step.reward, steps + 1
    assert steps == env.total_steps == data.num_tasks + data.num_windows and step.terminated
    assert accepted(step.result, data, 'fixed') == round(-total * 100)
    with pytest.raises(RuntimeError):
        env.step(legal[0])


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('fixture', ['large', 'periodic'])
def test_metaheuristic_plans_replay_through_the_environment(mode, fixture, request):
    data = request.getfixturevalue(fixture)
    outcome = solve_metaheuristic(data, mode=mode, algorithm='IGA', evaluations=300)
    assert len(actions_for_plan(outcome.result, data, mode)) == data.num_tasks + data.num_windows
    tampered = outcome.result
    tampered.total_tardiness += 1
    with pytest.raises(ValueError):
        actions_for_plan(tampered, data, mode)


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('fixture', ['large', 'periodic', 'periodic_big'])
def test_sequence_env_matches_the_decoder_on_random_episodes(mode, fixture, request):
    data, rng = request.getfixturevalue(fixture), random.Random(5)
    for _ in range(3):
        env = SequenceEnv(data, mode=mode)
        while not env.done:
            legal, rows = env.candidates()
            assert rows.shape == (len(legal), SEQUENCE_FEATURE_COUNT) and np.all(np.isfinite(rows))
            env.step(rng.choice(legal))
        listed = set(env.sequence)
        full = env.sequence + [t for t in range(env.n, env.decoder.size) if t not in listed]
        assert accepted(env.result, data, mode) == env.total == decoded_value(data, mode, full)
    with pytest.raises(RuntimeError):
        env.step(0)


@pytest.mark.parametrize('mode', MODES)
def test_sequence_env_replays_metaheuristic_sequences(mode, periodic):
    for algorithm in ('IGA', 'SA'):
        outcome = solve_metaheuristic(periodic, mode=mode, algorithm=algorithm, evaluations=400, seed=1)
        actions = teacher_actions(list(outcome.sequence), periodic, mode)
        env = SequenceEnv(periodic, mode=mode)
        for action in actions:
            step = env.step(action)
        assert step.terminated and accepted(step.result, periodic, mode) == outcome.result.total_tardiness
