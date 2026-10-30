"""Non-delay EDD/MDD/ATC dispatching on the R1 construction environment.

At each step the candidate tasks are those whose machine is free earliest
among legal production actions; the rule key picks one. A pending
maintenance whose start is earlier than that machine's tail goes first,
as in ``rules.py``. MDD (modified due date) and ATC (apparent tardiness
cost) are classic total-tardiness rules and are stronger baselines than
EDD on the G3 cases. ``rules.py`` stays byte-identical (hash-bound).
"""

import math
import statistics

from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.result import MaintenanceScheduleResult
from src.graduation.rl_environment import (
    MAINTENANCE_OFFSET, MAX_MACHINES, EpisodeInvariantError, ParallelMaintenanceEnv,
)

DISPATCH_RULES = ('EDD', 'MDD', 'ATC')
ATC_K = 1.0
# Nine rule variants: the compute-matched baseline for nine policy rollouts.
RULE_PORTFOLIO = (('EDD', ATC_K), ('MDD', ATC_K), *(('ATC', k) for k in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)))


def maintenance_start(env: ParallelMaintenanceEnv, machine: int) -> int:
    item = env.data.maintenance[machine]
    return item.fixed_start if env.mode == 'fixed' else max(env.machine_tails[machine], item.window_start)


def rule_action(env: ParallelMaintenanceEnv, legal: list[int], rule: str, *, atc_k: float = ATC_K) -> int:
    """Return the rule's action among the given legal actions."""
    if rule not in DISPATCH_RULES:
        raise ValueError(f'rule must be one of {DISPATCH_RULES}')
    if type(atc_k) not in (int, float) or not math.isfinite(atc_k) or atc_k <= 0:
        raise ValueError('atc_k must be finite and positive')
    tails, data = env.machine_tails, env.data
    production = [a for a in legal if a < MAINTENANCE_OFFSET]
    maintenance = [a for a in legal if a >= MAINTENANCE_OFFSET]
    first = min(maintenance, key=lambda a: (maintenance_start(env, a - MAINTENANCE_OFFSET), a)) if maintenance else None
    if not production:
        if first is None:
            raise EpisodeInvariantError('No legal action for the dispatch rule')
        return first
    earliest = min(tails[a % MAX_MACHINES] for a in production)
    candidates = [a for a in production if tails[a % MAX_MACHINES] == earliest]
    pbar = statistics.fmean(task.processing_time for task in data.tasks)

    def key(action):
        job, machine = divmod(action, MAX_MACHINES)
        t, p, d = tails[machine], data.tasks[job].processing_time, data.tasks[job].due_date
        if rule == 'EDD':
            return (d, p, action)
        if rule == 'MDD':
            return (max(d, t + p), p, action)
        return (-math.exp(-max(0, d - p - t) / (atc_k * pbar)) / p, action)

    action = min(candidates, key=key)
    if first is not None and maintenance_start(env, first - MAINTENANCE_OFFSET) < tails[action % MAX_MACHINES]:
        return first
    return action


def solve_dispatch_rule(data: ParallelMaintenanceInstance, *, mode: str, rule: str,
                        atc_k: float = ATC_K) -> MaintenanceScheduleResult:
    """Construct one complete plan; the environment G1-checks the terminal plan."""
    env = ParallelMaintenanceEnv(data, mode=mode)
    for _ in range(len(data.tasks) + data.num_machines):
        legal = [a for a, ok in enumerate(env.action_masks()) if ok]
        step = env.step(rule_action(env, legal, rule, atc_k=atc_k))
        if step.terminated:
            return step.result
    raise EpisodeInvariantError('Dispatch rule did not terminate within n+m steps')
