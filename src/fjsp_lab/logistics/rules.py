"""Rule baselines for the L1 logistics model.

* Joint rule ``EFT``: among all (job, machine, vehicle) decisions pick the
  earliest estimated finish of the next operation, which accounts for empty
  travel, loaded travel and the destination's queue at once.
* Decoupled rules ``<job rule>+NV``: first choose the job (FIFO, SPT or
  MWKR) and its machine as if transport were free (earliest machine-ready +
  processing time), then the nearest idle vehicle (NV, earliest pickup).
  They model "schedule production first, then dispatch vehicles".
* ``RANDOM``: uniform over the current decisions (seeded).

Every rule returns a schedule only after the logistics checker accepts it.
"""

from __future__ import annotations

import random
from typing import Callable

from fjsp_lab.logistics.instance import LogisticsInstance
from fjsp_lab.logistics.schedule import LogisticsSchedule
from fjsp_lab.logistics.simulator import Candidate, LogisticsSimulator, Policy, simulate


def _joint_eft(sim: LogisticsSimulator, options: list[Candidate]) -> Candidate:
    return min(options, key=lambda c: (c.finish, c.pickup, c.job, c.machine, c.vehicle if c.vehicle is not None else -1))


def _remaining_work(sim: LogisticsSimulator, job: int) -> int:
    production = sim.instance.production
    operations = production.jobs[job].operations
    return sum(min(p for _, p in operations[o].machine_options) for o in range(sim.next_op[job], len(operations)))


_JOB_KEYS: dict[str, Callable[[LogisticsSimulator, Candidate], tuple]] = {
    'FIFO': lambda sim, c: (sim.ready[c.job], c.job),
    'SPT': lambda sim, c: (c.processing_time, c.job),
    'MWKR': lambda sim, c: (-_remaining_work(sim, c.job), c.job),
}


def _decoupled(job_rule: str) -> Policy:
    job_key = _JOB_KEYS[job_rule]

    def policy(sim: LogisticsSimulator, options: list[Candidate]) -> Candidate:
        # Stage 1: job and machine, ignoring transport (a stay is ready now).
        def production_key(c: Candidate) -> tuple:
            ready = sim.now if c.vehicle is None else c.machine_ready
            return job_key(sim, c) + (ready + c.processing_time, c.machine)
        chosen = min(options, key=production_key)
        # Stage 2: nearest vehicle for that job and machine.
        same = [c for c in options if (c.job, c.machine) == (chosen.job, chosen.machine)]
        return min(same, key=lambda c: (c.pickup, c.vehicle if c.vehicle is not None else -1))

    return policy


def _random(seed: int) -> Policy:
    rng = random.Random(seed)
    return lambda sim, options: options[rng.randrange(len(options))]


RULES = ('EFT', 'FIFO+NV', 'SPT+NV', 'MWKR+NV', 'RANDOM')


def solve_rule(instance: LogisticsInstance, rule: str, *, seed: int = 0) -> LogisticsSchedule:
    """Simulate ``instance`` under one rule; raises SimulationDeadlock if the rule deadlocks."""
    if rule == 'EFT':
        policy = _joint_eft
    elif rule == 'RANDOM':
        policy = _random(seed)
    elif rule.endswith('+NV') and rule[:-3] in _JOB_KEYS:
        policy = _decoupled(rule[:-3])
    else:
        raise ValueError(f'Unknown rule {rule!r}; expected one of {RULES}')
    return simulate(instance, policy)
