"""Hand-derived policy expectations; these are construction rules, not optimizers."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import random

import pytest

from src.graduation import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation import check_parallel_maintenance_feasibility
from tests.graduation_helpers import one_machine, two_machines


def instance(p, d, machines=1):
    return ParallelMaintenanceInstance(tuple(ProductionTask(j, time, due) for j, (time, due) in enumerate(zip(p, d))),
        machines, tuple(MaintenanceRequirement(m, 1, 0, sum(p) + 1, 0) for m in range(machines)))


@pytest.mark.parametrize('rule,want', [('EDD', (4, 0, 8)), ('SPT', (8, 4, 0))])
def test_primary_due_date_and_processing_time_priorities_differ(rule, want):
    from src.graduation.rules import run_maintenance_rule_episode
    data = instance((3, 2, 1), (4, 2, 8))
    episode = run_maintenance_rule_episode(data, mode='joint', rule=rule)
    assert episode.actions[:3] == want


@pytest.mark.parametrize('rule,p,d,want', [
    ('EDD', (3, 1, 1), (5, 5, 5), (4, 8, 0)),
    ('SPT', (1, 1, 1), (5, 2, 2), (4, 8, 0)),
])
def test_secondary_priority_and_job_id_break_ties(rule, p, d, want):
    from src.graduation.rules import run_maintenance_rule_episode
    assert run_maintenance_rule_episode(instance(p, d), mode='joint', rule=rule).actions[:3] == want


def test_machine_selection_uses_earliest_tail_then_machine_id():
    from src.graduation.rules import run_maintenance_rule_episode
    data = instance((3, 1, 2, 1), (0, 1, 2, 3), machines=2)
    episode = run_maintenance_rule_episode(data, mode='joint', rule='EDD')
    assert episode.actions == (0, 5, 9, 12, 97, 96)


@pytest.mark.parametrize('builder,mode,want,actions', [
    (one_machine, 'fixed', 4, (96, 0, 4)), (one_machine, 'joint', 0, (0, 4, 96)),
    (two_machines, 'fixed', 6, (96, 97, 0, 5, 8)),
    (two_machines, 'joint', 0, (0, 5, 8, 97, 96)),
])
@pytest.mark.parametrize('rule', ['EDD', 'SPT'])
def test_hand_calculated_fixed_and_joint_policies_replay_only_legal_actions(builder, mode, want, actions, rule):
    from src.graduation.rules import run_maintenance_rule_episode
    from src.graduation import ParallelMaintenanceEnv
    data, _ = builder()
    episode = run_maintenance_rule_episode(data, mode=mode, rule=rule)
    assert episode.actions == actions
    assert episode.result.total_tardiness == want
    assert episode.total_reward == pytest.approx(-want / 100)
    env = ParallelMaintenanceEnv(data, mode=mode)
    for action in episode.actions:
        assert env.action_masks()[action]
        step = env.step(action)
    assert step.terminated and len(episode.actions) == len(data.tasks) + data.num_machines
    assert check_parallel_maintenance_feasibility(episode.result, data, mode=mode) == (True, [])


def test_integer_machine_tails_are_readonly_detached_snapshots():
    from src.graduation import ParallelMaintenanceEnv
    large = 2**40 + 1
    env = ParallelMaintenanceEnv(instance((large, large + 1), (large, large), machines=2), mode='joint')
    before = env.machine_tails
    env.step(0)
    env.step(5)
    assert before == (0, 0)
    assert env.machine_tails == (large, large + 1)
    assert all(type(value) is int for value in env.machine_tails)
    with pytest.raises(AttributeError):
        env.machine_tails = (0, 0)
    env.reset()
    assert env.machine_tails == (0, 0)


def test_maintenance_on_another_machine_precedes_later_production_but_equal_start_favors_production():
    from src.graduation.rules import run_maintenance_rule_episode
    # Machine 0 opens at 4; maintenance on machine 1 starts at 1, so open it first.
    data = ParallelMaintenanceInstance((ProductionTask(0, 2, 2), ProductionTask(1, 2, 4)), 2,
        (MaintenanceRequirement(0, 4, 0, 4, 0), MaintenanceRequirement(1, 1, 1, 2, 1)))
    episode = run_maintenance_rule_episode(data, mode='fixed', rule='EDD')
    assert episode.actions == (96, 97, 1, 4)
    # Joint production and maintenance both start at zero: production wins.
    equal = ParallelMaintenanceInstance((ProductionTask(0, 1, 1),), 2,
        tuple(MaintenanceRequirement(m, 1, 0, 3, 0) for m in range(2)))
    assert run_maintenance_rule_episode(equal, mode='joint', rule='EDD').actions == (0, 97, 96)


def test_without_production_choose_earliest_maintenance_start_before_machine_id():
    from src.graduation.rules import run_maintenance_rule_episode
    data = ParallelMaintenanceInstance((ProductionTask(0, 3, 3),), 2,
        (MaintenanceRequirement(0, 1, 2, 3, 2), MaintenanceRequirement(1, 1, 0, 1, 0)))
    assert run_maintenance_rule_episode(data, mode='fixed', rule='EDD').actions == (97, 1, 96)


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
@pytest.mark.parametrize('rule', ['EDD', 'SPT', 'Random'])
def test_idle_machines_and_late_maintenance_are_completed_without_inflating_makespan(mode, rule):
    from src.graduation.rules import run_maintenance_rule_episode
    idle = ParallelMaintenanceInstance((ProductionTask(0, 2, 2),), 2,
        tuple(MaintenanceRequirement(m, 2, 0, 2, 0) for m in range(2)))
    episode = run_maintenance_rule_episode(idle, mode=mode, rule=rule)
    assert len(episode.actions) == 3 and len(episode.result.maintenance_records) == 2
    assert episode.result.total_tardiness == 2
    late = ParallelMaintenanceInstance((ProductionTask(0, 1, 1),), 1, (MaintenanceRequirement(0, 1, 3, 4, 3),))
    episode = run_maintenance_rule_episode(late, mode=mode, rule=rule)
    assert episode.result.makespan == 1 and episode.result.total_tardiness == 0
    assert episode.result.maintenance_records[0].end == 4


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
@pytest.mark.parametrize('rule', ['EDD', 'SPT', 'Random'])
def test_maximum_supported_inputs_preserve_every_task_and_maintenance(mode, rule):
    from src.graduation.rules import run_maintenance_rule_episode
    data = instance((1,) * 24, tuple(range(24)), machines=4)
    episode = run_maintenance_rule_episode(data, mode=mode, rule=rule, seed=2**32 - 1)
    assert len(episode.actions) == 28 and len(episode.result.records) == 24
    assert len(episode.result.maintenance_records) == 4
    assert check_parallel_maintenance_feasibility(episode.result, data, mode=mode) == (True, [])


def test_random_replays_sorted_legal_actions_with_local_rng_and_preserves_inputs():
    from src.graduation.rules import run_maintenance_rule_episode
    from src.graduation import ParallelMaintenanceEnv
    data, _ = two_machines()
    before, global_state = deepcopy(data), random.getstate()
    episode = run_maintenance_rule_episode(data, mode='joint', rule='Random', seed=42)
    # Sorted initial choices are [0, 1, 4, 5, 8, 9, 96, 97]; seed42 selects index1.
    assert episode.actions[0] == 1
    env, rng = ParallelMaintenanceEnv(data, mode='joint'), random.Random(42)
    for action in episode.actions:
        assert action == rng.choice([i for i, legal in enumerate(env.action_masks()) if legal])
        env.step(action)
    assert run_maintenance_rule_episode(data, mode='joint', rule='Random', seed=42) == episode
    assert data == before and random.getstate() == global_state


def test_random_includes_maintenance_in_initial_choice():
    from src.graduation.rules import run_maintenance_rule_episode
    data, _ = one_machine()
    assert run_maintenance_rule_episode(data, mode='joint', rule='Random', seed=42).actions[0] == 96


def test_edd_skips_a_higher_priority_job_with_no_legal_machine():
    from src.graduation.rules import run_maintenance_rule_episode
    data = ParallelMaintenanceInstance((ProductionTask(0, 4, 0), ProductionTask(1, 1, 9)), 1,
        (MaintenanceRequirement(0, 1, 3, 4, 3),))
    assert run_maintenance_rule_episode(data, mode='fixed', rule='EDD').actions == (4, 96, 0)


@pytest.mark.parametrize('rule', ['EDD', 'SPT', 'Random'])
@pytest.mark.parametrize('seed', [True, False, -1, 2**32, 1.0, '42', None])
def test_invalid_seed_rejects_for_every_rule(rule, seed):
    from src.graduation.rules import run_maintenance_rule_episode
    with pytest.raises(ValueError):
        run_maintenance_rule_episode(instance((1,), (1,)), mode='joint', rule=rule, seed=seed)


@pytest.mark.parametrize('rule', ['edd', 'random', '', None, [], 3])
def test_invalid_rule_rejects(rule):
    from src.graduation.rules import run_maintenance_rule_episode
    with pytest.raises(ValueError):
        run_maintenance_rule_episode(instance((1,), (1,)), mode='joint', rule=rule)


def test_public_wrapper_returns_detached_mutable_result_without_solver_certificate():
    from src.graduation import RuleEpisode, run_maintenance_rule_episode, solve_maintenance_rule
    data, _ = one_machine()
    episode = run_maintenance_rule_episode(data, mode='joint', rule='EDD', seed=0)
    assert isinstance(episode, RuleEpisode) and (episode.rule, episode.mode, episode.seed) == ('EDD', 'joint', 0)
    with pytest.raises(FrozenInstanceError):
        episode.seed = 1
    result = solve_maintenance_rule(data, mode='joint', rule='EDD', seed=0)
    assert result == episode.result and result is not episode.result
    for field in ('solver_status', 'solver_objective_value', 'solver_objective_bound', 'solver_gap', 'solver_wall_time'):
        assert getattr(result, field) is None
    episode.result.records.clear()
    assert len(result.records) == 2


def test_terminal_invariant_failure_propagates_without_partial_result(monkeypatch):
    from src.graduation import rl_environment, EpisodeInvariantError, MaintenanceViolation
    from src.graduation.rules import run_maintenance_rule_episode
    monkeypatch.setattr(rl_environment, 'check_parallel_maintenance_feasibility',
        lambda *a, **k: (False, [MaintenanceViolation('REFUSED', 'controlled refusal')]))
    with pytest.raises(EpisodeInvariantError):
        run_maintenance_rule_episode(instance((1,), (1,)), mode='joint', rule='EDD')
