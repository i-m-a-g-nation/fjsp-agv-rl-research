"""Finite EDD, SPT and local-seed Random policies for the R1 constructor."""

from dataclasses import dataclass
import random

from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.result import MaintenanceScheduleResult
from src.graduation.rl_environment import (
    EpisodeInvariantError, MAINTENANCE_OFFSET, MAX_MACHINES, ParallelMaintenanceEnv,
)


@dataclass(frozen=True)
class RuleEpisode:
    """Frozen trace wrapper; result is a detached, deliberately mutable schedule."""

    rule: str
    mode: str
    seed: int
    actions: tuple[int, ...]
    total_reward: float
    result: MaintenanceScheduleResult


def _priority_action(env: ParallelMaintenanceEnv, legal: list[int], rule: str) -> int:
    tails = env.machine_tails
    production = [action for action in legal if action < MAINTENANCE_OFFSET]
    maintenance = [action for action in legal if action >= MAINTENANCE_OFFSET]

    def maintenance_key(action):
        machine = action - MAINTENANCE_OFFSET
        item = env.data.maintenance[machine]
        start = item.fixed_start if env.mode == 'fixed' else max(tails[machine], item.window_start)
        return start, machine

    first_maintenance = min(maintenance, key=maintenance_key) if maintenance else None
    if not production:
        return first_maintenance
    jobs = {action // MAX_MACHINES for action in production}

    def task_key(job):
        task = env.data.tasks[job]
        if rule == 'EDD':
            return task.due_date, task.processing_time, job
        return task.processing_time, task.due_date, job

    job = min(jobs, key=task_key)
    selected = min((action for action in production if action // MAX_MACHINES == job),
                   key=lambda action: (tails[action % MAX_MACHINES], action % MAX_MACHINES))
    if first_maintenance is not None and maintenance_key(first_maintenance)[0] < tails[selected % MAX_MACHINES]:
        return first_maintenance
    return selected


def run_maintenance_rule_episode(
    data: ParallelMaintenanceInstance, *, mode: str, rule: str, seed: int = 42,
) -> RuleEpisode:
    """Return only a complete R1/G1 accepted episode; propagate construction errors."""
    if rule not in ('EDD', 'SPT', 'Random'):
        raise ValueError('rule must be EDD, SPT or Random')
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('seed must be a non-bool integer in 0..2**32-1')
    env, rng = ParallelMaintenanceEnv(data, mode=mode), random.Random(seed)
    actions, total_reward = [], 0.0
    for _ in range(len(data.tasks) + data.num_machines):
        legal = [action for action, valid in enumerate(env.action_masks()) if valid]
        action = rng.choice(legal) if rule == 'Random' else _priority_action(env, legal, rule)
        step = env.step(action)
        actions.append(action)
        total_reward += step.reward
        if step.terminated:
            return RuleEpisode(rule, mode, seed, tuple(actions), total_reward, env.get_result())
    raise EpisodeInvariantError('Rule did not reach an accepted terminal state within n+m transitions')


def solve_maintenance_rule(
    data: ParallelMaintenanceInstance, *, mode: str, rule: str, seed: int = 42,
) -> MaintenanceScheduleResult:
    """Unified algorithm result, with no solver status or optimality certificate."""
    return run_maintenance_rule_episode(data, mode=mode, rule=rule, seed=seed).result
