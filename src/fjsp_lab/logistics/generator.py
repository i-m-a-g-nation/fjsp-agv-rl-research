"""Deterministic training and validation instances for the L2 learned policy.

Each instance seed fixes: 5-10 jobs of 2-5 operations; per operation 1-2
eligible machines with independent processing times in 5..30; a machine
count from the layouts supplied by the caller (travel matrices with the L/U
station as last location, e.g. from ``parse_layout``); 2 vehicles; no
return to L/U; and one of the five L1 configurations (benchmark
conventions, or blocking with input buffers inf / 2 / 1 / 0). The library
reads no data files; layouts come from the caller.

Seed ranges are disjoint: training 100000-, validation 200000-.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Mapping, Sequence

from fjsp_lab.fjsp.instance import FJSPInstance
from fjsp_lab.logistics.instance import LogisticsInstance

CONFIGS = {'bench': (False, None), 'block-inf': (True, None), 'block-2': (True, 2),
           'block-1': (True, 1), 'block-0': (True, 0)}               # name: (blocking, buffer capacity)
SPLITS = {'train': 100000, 'validation': 200000}


@dataclass(frozen=True)
class GeneratedInstance:
    seed: int
    config: str
    data: LogisticsInstance


def generate(seed: int, layouts: Mapping[int, Sequence[Sequence[int]]]) -> GeneratedInstance:
    """One instance; ``layouts`` maps a machine count to its travel matrix (L/U last)."""
    if not layouts:
        raise ValueError('At least one layout is needed')
    rng = random.Random(seed)
    machines = rng.choice(sorted(layouts))
    jobs = []
    for _ in range(rng.randint(5, 10)):
        operations = []
        for _ in range(rng.randint(2, 5)):
            eligible = rng.sample(range(machines), rng.randint(1, min(2, machines)))
            operations.append([(m, rng.randint(5, 30)) for m in sorted(eligible)])
        jobs.append(operations)
    config = rng.choice(sorted(CONFIGS))
    blocking, buffer = CONFIGS[config]
    production = FJSPInstance.from_jobs_array(jobs, num_machines=machines)
    data = LogisticsInstance.create(production, layouts[machines], num_vehicles=2, buffer_capacity=buffer,
                                    blocking=blocking, return_to_lu=False)
    return GeneratedInstance(seed, config, data)


def split(name: str, count: int, layouts: Mapping[int, Sequence[Sequence[int]]]) -> list[GeneratedInstance]:
    """The first ``count`` instances of a split ('train' or 'validation')."""
    if name not in SPLITS or count < 0:
        raise ValueError(f'Split must be one of {sorted(SPLITS)} and count >= 0')
    return [generate(SPLITS[name] + i, layouts) for i in range(count)]
