"""Deterministic instance generator (G3A) and the standard instance sets.

Per (n, seed) the base workload draws, from SHA-256 derived seeds,
processing times p_j in [1, 20], due quantiles u_j in [50, 150] and four
maintenance-start quantiles v in [0, 25]. Then for m machines and factors
alpha (maintenance length), beta (window slack) and tau (due tightness):

    W   = ceil(sum p / m)              base load
    q_i = max(1, ceil(alpha W / 100))  maintenance duration
    s_i = ceil(beta W / 100)           window slack
    L_i = floor(v_i W / 100),  U_i = L_i + q_i + s_i
    d_j = ceil(tau W u_j / 10000)
    f_i = L_i + floor(s_i / 2)         fixed start (midpoint; earliest = L_i, latest = L_i + s_i)

``g3a_cases`` is the 240-pair factorial grid; ``sample_instances`` draws
the random training/validation/test sets used by the learning methods.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import product
import random

from fjsp_lab.maintenance.instance import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask

PROCESSING_RANGE = (1, 20)
DUE_QUANTILE_RANGE = (50, 150)
START_QUANTILE_RANGE = (0, 25)
START_DRAWS = 4
SEED_KEY = 'graduation-g3a-v1|n={n}|seed={seed}|field={field}'
FIXED_POLICIES = ('window_midpoint', 'window_earliest', 'window_latest')

# The 2^5 primary grid (x 5 seeds) and the n8-m2 fixed-policy sensitivity set.
PRIMARY = {'num_tasks': (8, 24), 'num_machines': (2, 4), 'alpha_percent': (10, 30),
           'beta_percent': (25, 75), 'tau_percent': (75, 125), 'instance_seeds': (101, 202, 303, 404, 505)}
SENSITIVITY_SIZE = (8, 2)
SENSITIVITY_POLICIES = ('window_earliest', 'window_latest')

# Sizes and factor levels of the randomly sampled learning sets.
SIZES = ((8, 2), (8, 4), (16, 2), (16, 4), (24, 2), (24, 4))


def _draws(n: int, seed: int, field: str, low: int, high: int, count: int) -> list[int]:
    key = SEED_KEY.format(n=n, seed=seed, field=field)
    rng = random.Random(int.from_bytes(hashlib.sha256(key.encode('utf-8')).digest()[:8], 'big'))
    return [rng.randint(low, high) for _ in range(count)]


def base_workload(n: int, seed: int) -> tuple[list[int], list[int], list[int]]:
    """(processing times, due quantiles, maintenance-start quantiles) for one (n, seed)."""
    return (_draws(n, seed, 'processing', *PROCESSING_RANGE, n),
            _draws(n, seed, 'due', *DUE_QUANTILE_RANGE, n),
            _draws(n, seed, 'maintenance_start', *START_QUANTILE_RANGE, START_DRAWS))


def build_instance(n: int, m: int, alpha: int, beta: int, tau: int, seed: int,
                   fixed_policy: str = 'window_midpoint') -> ParallelMaintenanceInstance:
    """One instance; every machine gets its window and a fixed start by ``fixed_policy``."""
    if fixed_policy not in FIXED_POLICIES:
        raise ValueError(f'fixed_policy must be one of {FIXED_POLICIES}')
    if not 1 <= m <= START_DRAWS:
        raise ValueError(f'The generator supports 1..{START_DRAWS} machines')
    p, u, v = base_workload(n, seed)
    w = (sum(p) + m - 1) // m
    q = max(1, (alpha * w + 99) // 100)
    slack = (beta * w + 99) // 100
    offset = {'window_midpoint': slack // 2, 'window_earliest': 0, 'window_latest': slack}[fixed_policy]
    tasks = tuple(ProductionTask(j, p[j], (tau * w * u[j] + 9999) // 10000) for j in range(n))
    maintenance = []
    for machine in range(m):
        start = v[machine] * w // 100
        maintenance.append(MaintenanceRequirement(machine, q, start, start + q + slack, start + offset))
    return ParallelMaintenanceInstance(tasks, m, tuple(maintenance))


@dataclass(frozen=True)
class Case:
    """A labelled instance of the G3A grid; every case is solved in both modes."""

    case_id: str
    group: str            # 'primary' or 'sensitivity'
    num_tasks: int
    num_machines: int
    alpha_percent: int
    beta_percent: int
    tau_percent: int
    instance_seed: int
    fixed_policy: str
    data: ParallelMaintenanceInstance


def _case(n, m, alpha, beta, tau, seed, policy, group) -> Case:
    case_id = f'g3a-main-n{n}-m{m}-a{alpha}-b{beta}-t{tau}-s{seed}-{policy.removeprefix("window_")}'
    return Case(case_id, group, n, m, alpha, beta, tau, seed, policy,
                build_instance(n, m, alpha, beta, tau, seed, policy))


def g3a_cases() -> list[Case]:
    """160 primary cases (n/m/alpha/beta/tau/seed order, midpoint), then 80 sensitivity cases.

    Each n8-m2 primary case is followed, in parent order, by its earliest and
    latest fixed-start variants. Equal physical data under different labels
    are kept: these are planned requests, not independent samples.
    """
    cases = [_case(n, m, a, b, t, s, 'window_midpoint', 'primary')
             for n, m, a, b, t, s in product(*PRIMARY.values())]
    for parent in list(cases):
        if (parent.num_tasks, parent.num_machines) != SENSITIVITY_SIZE:
            continue
        for policy in SENSITIVITY_POLICIES:
            cases.append(_case(parent.num_tasks, parent.num_machines, parent.alpha_percent, parent.beta_percent,
                               parent.tau_percent, parent.instance_seed, policy, 'sensitivity'))
    return cases


@dataclass(frozen=True)
class SampledInstance:
    data: ParallelMaintenanceInstance
    mode: str
    num_tasks: int
    num_machines: int
    alpha_percent: int
    beta_percent: int
    tau_percent: int
    seed: int


def sample_instances(seeds: range, *, sampler_seed: int, sizes=SIZES, balanced: bool = False) -> list[SampledInstance]:
    """Draw size, factors and mode per instance seed (balanced cycles through the sizes)."""
    rng = random.Random(sampler_seed)
    instances = []
    for index, seed in enumerate(seeds):
        n, m = sizes[index % len(sizes)] if balanced else rng.choice(sizes)
        alpha, beta, tau = rng.choice((10, 30)), rng.choice((25, 75)), rng.choice((75, 125))
        mode = rng.choice(('fixed', 'joint'))
        instances.append(SampledInstance(build_instance(n, m, alpha, beta, tau, seed), mode,
                                         n, m, alpha, beta, tau, seed))
    return instances


# Learning splits: disjoint instance-seed ranges, (seeds, sampler_seed, balanced).
SPLITS = {
    'train': (range(10000, 12000), 1, False),            # scoring policy
    'validation': (range(20000, 20200), 2, False),       # checkpoint selection only
    'test': (range(30000, 30600), 3, True),              # 100 per size, touched once
    'teacher_train': (range(100000, 120000), 11, False),  # attention policy (IGA teacher)
}


def split_instances(name: str) -> list[SampledInstance]:
    seeds, sampler_seed, balanced = SPLITS[name]
    return sample_instances(seeds, sampler_seed=sampler_seed, balanced=balanced)
