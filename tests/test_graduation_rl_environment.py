from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from src.graduation import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from tests.graduation_helpers import one_machine, two_machines


@pytest.mark.parametrize('builder,mode,actions,want', [
    (one_machine, 'fixed', [96, 0, 4], 4), (one_machine, 'joint', [0, 4, 96], 0),
    (two_machines, 'fixed', [96, 97, 0, 5, 8], 6),
    (two_machines, 'joint', [0, 5, 8, 96, 97], 0),
])
def test_literal_trajectories_preserve_maintenance_legality_and_exact_tardiness_return(builder, mode, actions, want):
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    from src.graduation import check_parallel_maintenance_feasibility
    data, _ = builder()
    env = ParallelMaintenanceEnv(data, mode=mode)
    rewards = []
    for index, action in enumerate(actions):
        assert env.action_masks()[action]
        step = env.step(action)
        rewards.append(step.reward)
        assert step.terminated is (index == len(actions)-1) and not step.truncated
        assert (step.result is not None) is step.terminated
    result = env.get_result()
    assert result.total_tardiness == want and result.solver_status is None
    assert sum(rewards) == pytest.approx(-want/100)
    assert check_parallel_maintenance_feasibility(result, data, mode=mode) == (True, [])
    assert env.observe().steps == len(data.tasks) + data.num_machines
    assert env.observe().status == 'TERMINATED' and not any(env.action_masks())


def test_observation_has_explicit_presence_masks_and_fixed_width_snapshots():
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    data, _ = one_machine(False, fixed_start=None)
    env = ParallelMaintenanceEnv(data, mode='joint')
    observation = env.reset()
    assert observation.scale == 4 and observation.mode == 'joint'
    assert len(observation.task_features) == 24 and len(observation.machine_features) == 4
    assert observation.task_presence == (True, True) + (False,)*22
    assert observation.machine_presence == (True,) + (False,)*3
    assert observation.task_features[0] == (0.5, 0.5, 0.0)
    assert observation.machine_features[0][4:] == (-1.0, 0.0, 0.0)
    assert observation.task_features[2] == (0.0, 0.0, 0.0)
    assert len(observation.action_mask) == 100
    assert [i for i, valid in enumerate(observation.action_mask) if valid] == [0, 4, 96]
    with pytest.raises(FrozenInstanceError): observation.steps = 99
    with pytest.raises(AttributeError): env.mode = 'fixed'
    env.step(0)
    assert observation.steps == 0 and observation.task_features[0][-1] == 0.0
    assert env.observe().task_features[0][-1] == 1.0


@pytest.mark.parametrize('action', [-1, 100, True, 0.0, '96', 1, 8, 97])
def test_invalid_or_padding_actions_reject_before_mutation(action):
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    data, _ = one_machine()
    env = ParallelMaintenanceEnv(data, mode='joint')
    before = env.observe()
    with pytest.raises(ValueError): env.step(action)
    assert env.observe() == before


def test_fixed_start_and_full_window_reservation_masks_allow_exact_touching():
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    data = ParallelMaintenanceInstance((ProductionTask(0, 2, 2), ProductionTask(1, 1, 3)), 1,
                                      (MaintenanceRequirement(0, 2, 0, 4, 2),))
    env = ParallelMaintenanceEnv(data, mode='fixed')
    env.step(0)
    assert not env.action_masks()[4] and env.action_masks()[96]
    before = env.observe()
    with pytest.raises(ValueError): env.step(4)
    assert env.observe() == before
    env.step(96)
    result = env.step(4).result
    assert result.maintenance_records[0].start == 2 and result.maintenance_records[0].end == 4
    assert result.records[1].start == 4


def test_all_production_is_not_terminal_until_idle_machine_maintenance_is_done():
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    data = ParallelMaintenanceInstance((ProductionTask(0, 1, 1),), 2,
        tuple(MaintenanceRequirement(i, 1, 0, 3, 0) for i in range(2)))
    env = ParallelMaintenanceEnv(data, mode='joint')
    assert not env.step(0).terminated
    assert not env.step(96).terminated
    with pytest.raises(RuntimeError): env.get_result()
    step = env.step(97)
    assert step.terminated and len(step.result.maintenance_records) == 2


def test_maintenance_waits_to_window_start_without_inflating_production_makespan():
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    data = ParallelMaintenanceInstance((ProductionTask(0, 1, 1),), 1, (MaintenanceRequirement(0, 1, 3, 4, 3),))
    env = ParallelMaintenanceEnv(data, mode='joint')
    env.step(0)
    result = env.step(96).result
    assert result.makespan == 1 and result.total_tardiness == 0
    assert (result.maintenance_records[0].start, result.maintenance_records[0].end) == (3, 4)


def test_result_and_reset_are_detached_and_duplicate_or_postterminal_steps_do_not_mutate():
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    data, _ = one_machine()
    env = ParallelMaintenanceEnv(data, mode='joint')
    initial = env.observe()
    env.step(0)
    before = env.observe()
    with pytest.raises(ValueError): env.step(0)
    assert env.observe() == before
    env.step(4)
    terminal = env.step(96)
    accepted = deepcopy(env.get_result())
    terminal.result.records.clear()
    changed = env.get_result()
    with pytest.raises(AttributeError):
        changed.instance.jobs.clear()
    # Even bypassing normal immutability on this returned copy must not touch
    # the environment's internal instance.
    object.__setattr__(changed.instance, 'jobs', ())
    assert env.get_result() == accepted
    with pytest.raises(RuntimeError): env.step(96)
    assert env.reset() == initial
    assert accepted.records and not any(env.observe().task_features[j][-1] for j in range(2))


def test_truncation_never_exposes_a_partial_or_unmaintained_zero_tardiness_result():
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    data, _ = one_machine()
    env = ParallelMaintenanceEnv(data, mode='joint')
    env.step(0)
    env.step(4)
    step = env.truncate()
    assert step.truncated and not step.terminated and step.result is None and step.reward == 0
    assert step.observation.status == 'TRUNCATED' and not any(env.action_masks())
    with pytest.raises(RuntimeError): env.get_result()
    with pytest.raises(RuntimeError): env.step(96)
    assert env.reset().status == 'ACTIVE'


def test_terminal_checker_refusal_cannot_expose_accepted_result(monkeypatch):
    from src.graduation import rl_environment as module
    from src.graduation import MaintenanceViolation
    data, _ = one_machine()
    env = module.ParallelMaintenanceEnv(data, mode='joint')
    env.step(0)
    env.step(4)
    monkeypatch.setattr(module, 'check_parallel_maintenance_feasibility',
                        lambda *a, **kw: (False, [MaintenanceViolation('DENIED', 'test refusal')]))
    with pytest.raises(module.EpisodeInvariantError): env.step(96)
    assert env.observe().status == 'FAILED' and not any(env.action_masks())
    with pytest.raises(RuntimeError): env.get_result()
    assert env.reset().status == 'ACTIVE'


@pytest.mark.parametrize('fault', ['mode', 'missing_fixed', 'tasks', 'machines', 'numeric'])
def test_environment_rejects_unsupported_configuration_without_cropping(fault):
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    data, _ = one_machine(fixed_start=None if fault == 'missing_fixed' else 0)
    if fault == 'tasks': data = ParallelMaintenanceInstance(tuple(ProductionTask(j, 1, 1) for j in range(25)), 1, data.maintenance)
    if fault == 'machines': data = ParallelMaintenanceInstance(data.tasks, 5,
        tuple(MaintenanceRequirement(m, 1, 0, 3, 0) for m in range(5)))
    if fault == 'numeric': data = ParallelMaintenanceInstance((ProductionTask(0, 2**60, 0),), 1, data.maintenance)
    with pytest.raises(ValueError): ParallelMaintenanceEnv(data, mode='wrong' if fault == 'mode' else 'fixed')
