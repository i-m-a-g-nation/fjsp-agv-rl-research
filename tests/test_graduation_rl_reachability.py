from copy import deepcopy
import random

import pytest

from src.graduation import (MaintenanceRequirement, ParallelMaintenanceEnv, ParallelMaintenanceInstance,
    ProductionTask, check_parallel_maintenance_feasibility, enumerate_parallel_maintenance)
from tests.graduation_helpers import one_machine, two_machines


def reachable_best(env):
    """Test-only complete action tree, never a production environment hook."""
    visited = 0
    leaves = 0
    def walk(current, rewards):
        nonlocal visited, leaves
        visited += 1
        assert visited <= 100000, 'Tiny validation search exceeded its explicit state budget'
        observation = current.observe()
        assert observation.steps == sum(row[2] for row in observation.task_features) + sum(row[5] for row in observation.machine_features)
        if observation.status == 'TERMINATED':
            leaves += 1
            result = current.get_result()
            assert check_parallel_maintenance_feasibility(result, current.data, mode=current.mode) == (True, [])
            assert rewards == pytest.approx(-result.total_tardiness/100)
            assert observation.steps == len(current.data.tasks) + current.data.num_machines
            return result.total_tardiness
        valid = [action for action, allowed in enumerate(current.action_masks()) if allowed]
        assert valid and observation.steps < len(current.data.tasks) + current.data.num_machines
        best = None
        for action in valid:
            child = deepcopy(current)
            step = child.step(action)
            assert step.observation.steps == observation.steps+1 and not step.truncated
            value = walk(child, rewards + step.reward)
            best = value if best is None else min(best, value)
        return best
    best = walk(env, 0.0)
    assert leaves > 0
    return best


@pytest.mark.parametrize('builder,mode,want', [(one_machine, 'fixed', 4), (one_machine, 'joint', 0),
                                              (two_machines, 'fixed', 6), (two_machines, 'joint', 0)])
def test_all_reachable_hand_example_plans_are_valid_and_preserve_optimal_value(builder, mode, want):
    data, _ = builder()
    assert reachable_best(ParallelMaintenanceEnv(data, mode=mode)) == want


@pytest.mark.parametrize('seed', range(6))
def test_all_tiny_action_tree_optima_match_independent_enumeration(seed, monkeypatch):
    from src.graduation import solver
    def forbidden(*a, **kw): pytest.fail('No CP-SAT call is allowed in R1 transitions or the independent oracle')
    monkeypatch.setattr(solver.cp_model, 'CpSolver', forbidden)
    rng = random.Random(seed)
    tasks = tuple(ProductionTask(j, rng.randint(1, 3), rng.randint(0, 8)) for j in range(1+seed%3))
    requirements = []
    for machine in range(1+seed%2):
        start, duration, slack = rng.randint(0, 2), rng.randint(1, 2), rng.randint(0, 2)
        requirements.append(MaintenanceRequirement(machine, duration, start, start+duration+slack,
                                                   start+rng.randint(0, slack)))
    data = ParallelMaintenanceInstance(tasks, len(requirements), tuple(requirements))
    original = deepcopy(data)
    for mode in ('fixed', 'joint'):
        reference = enumerate_parallel_maintenance(data, mode=mode)
        assert reachable_best(ParallelMaintenanceEnv(data, mode=mode)) == reference.total_tardiness
    assert data == original


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
@pytest.mark.parametrize('seed', [7, 42, 99])
def test_maximum_size_legal_trajectories_finish_in_28_steps_and_reset_reproducibly(mode, seed):
    data = ParallelMaintenanceInstance(tuple(ProductionTask(j, 1+j%5, 3*j) for j in range(24)), 4,
        tuple(MaintenanceRequirement(i, i+1, i, 18+i+(i+1), 12+i) for i in range(4)))
    env = ParallelMaintenanceEnv(data, mode=mode)
    def rollout():
        rng = random.Random(seed)
        total, actions = 0.0, []
        for index in range(28):
            mask = env.action_masks()
            assert any(mask)
            action = rng.choice([a for a, allowed in enumerate(mask) if allowed])
            actions.append(action)
            step = env.step(action)
            total += step.reward
            assert step.terminated is (index == 27)
        result = env.get_result()
        assert check_parallel_maintenance_feasibility(result, data, mode=mode) == (True, [])
        assert total == pytest.approx(-sum(max(0, r.end-data.tasks[r.job_id].due_date) for r in result.records)/100)
        assert len(result.records) == 24 and len(result.maintenance_records) == 4
        return result, actions
    first = rollout()
    env.reset()
    assert rollout() == first
