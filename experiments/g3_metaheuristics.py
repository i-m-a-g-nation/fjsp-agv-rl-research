"""Graduation: GA, SA and improved GA on the 240 G3A cases x 2 modes.

Default settings of fjsp_lab.maintenance.metaheuristics (no tuning); budgets
of 1 000, 10 000 and 50 000 decodes; seeds 0-4 for every (instance,
algorithm, budget). Every returned plan is re-checked. Per instance and
method, rows.csv holds the mean, best and worst over seeds and the mean
seconds per run. The cross-method comparison is g4_comparison.py.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import logging
import statistics
import time

from _common import checked_tardiness, parse_args, provenance, write_csv, write_json

from fjsp_lab.maintenance.generator import g3a_cases
from fjsp_lab.maintenance.metaheuristics import ALGORITHMS, DEFAULT_SETTINGS, solve_metaheuristic

LOGGER = logging.getLogger(__name__)
BUDGETS = (1000, 10000, 50000)
SEEDS = (0, 1, 2, 3, 4)
PROCESSES = 4


def run_instance(job) -> dict:
    case, mode, budgets = job
    row = {'case_id': case.case_id, 'mode': mode}
    for algorithm in ALGORITHMS:
        for budget in budgets:
            values, seconds = [], []
            for seed in SEEDS:
                started = time.perf_counter()
                outcome = solve_metaheuristic(case.data, mode=mode, algorithm=algorithm, evaluations=budget, seed=seed)
                seconds.append(time.perf_counter() - started)
                values.append(checked_tardiness(outcome.result, case.data, mode))
            name = f'{algorithm}_{budget}'
            row.update({name: statistics.fmean(values), f'{name}_best': min(values), f'{name}_worst': max(values),
                        f'{name}_seconds': statistics.fmean(seconds)})
    return row


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g3_metaheuristics',
                      lambda p: p.add_argument('--budgets', type=int, nargs='+', default=list(BUDGETS)))
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    started = time.monotonic()
    jobs = [(case, mode, tuple(args.budgets)) for case in g3a_cases() for mode in ('fixed', 'joint')]
    with ProcessPoolExecutor(max_workers=PROCESSES) as pool:
        rows = list(pool.map(run_instance, jobs, chunksize=4))
    write_csv(args.output_dir / 'rows.csv', rows)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g3_metaheuristics', 'algorithms': ALGORITHMS, 'settings': DEFAULT_SETTINGS,
        'budgets': args.budgets, 'seeds': SEEDS, 'instances': len(rows),
        'runs': len(rows) * len(ALGORITHMS) * len(args.budgets) * len(SEEDS), 'parallel_processes': PROCESSES,
        'elapsed_seconds': round(time.monotonic() - started, 1), **provenance(__file__)})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
