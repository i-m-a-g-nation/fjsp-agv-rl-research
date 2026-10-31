"""Non-delay dispatching rules EDD, MDD and ATC on the construction environment.

At each step the candidate jobs are the legal production actions on the
machine(s) that become free earliest; the rule key picks one. A pending
maintenance whose start is earlier than that machine's tail goes first.

* EDD: earliest due date d_j;
* MDD (Baker & Bertrand 1982): modified due date max(d_j, t + p_j);
* ATC (Vepsalainen & Morton 1987): max exp(-max(0, d_j - p_j - t) / (k p_bar)) / p_j.
"""

from __future__ import annotations

import math
import statistics

from fjsp_lab.maintenance.env import MAINTENANCE_OFFSET, MAX_MACHINES, EpisodeInvariantError, ParallelMaintenanceEnv
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult

DISPATCH_RULES = ('EDD', 'MDD', 'ATC')
ATC_K = 1.0
# Nine rule variants: the compute-matched baseline for nine policy rollouts.
RULE_PORTFOLIO = (('EDD', ATC_K), ('MDD', ATC_K), *(('ATC', k) for k in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)))


def rule_action(env: ParallelMaintenanceEnv, legal: list[int], rule: str, *, atc_k: float = ATC_K) -> int:
    """Return the rule's action among the given legal actions."""
    if rule not in DISPATCH_RULES:
        raise ValueError(f'rule must be one of {DISPATCH_RULES}')
    if type(atc_k) not in (int, float) or not math.isfinite(atc_k) or atc_k <= 0:
        raise ValueError('atc_k must be finite and positive')
    tails, data = env.machine_tails, env.data
    production = [a for a in legal if a < MAINTENANCE_OFFSET]
    maintenance = [a for a in legal if a >= MAINTENANCE_OFFSET]
    first = min(maintenance, key=lambda a: (env.maintenance_start(a - MAINTENANCE_OFFSET), a)) if maintenance else None
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
    if first is not None and env.maintenance_start(first - MAINTENANCE_OFFSET) < tails[action % MAX_MACHINES]:
        return first
    return action


def solve_dispatch_rule(data: ParallelMaintenanceInstance, *, mode: str, rule: str,
                        atc_k: float = ATC_K) -> MaintenanceScheduleResult:
    """Construct one complete plan; the environment checks the terminal plan."""
    env = ParallelMaintenanceEnv(data, mode=mode)
    for _ in range(len(data.tasks) + data.num_machines):
        step = env.step(rule_action(env, env.legal_actions(), rule, atc_k=atc_k))
        if step.terminated:
            return step.result
    raise EpisodeInvariantError('Dispatch rule did not terminate within n+m steps')
