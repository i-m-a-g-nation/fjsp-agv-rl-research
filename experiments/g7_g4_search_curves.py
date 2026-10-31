"""Graduation G4: anytime curves of rules, GA/SA/IGA and CP-SAT on the 576 G4 test instances.

Per instance (case x mode), in one worker process so every method runs under
the same conditions:
* EDD, MDD, ATC (k=1): one construction each, timed;
* IGA and GA: one 10 s run (seed 0) recording (seconds, decodes, best) at every improvement;
* SA: one run per time budget (its cooling depends on the budget);
* CP-SAT: 60 s, 1 worker, seed 42, recording every incumbent (objective, bound).
Every returned plan is re-checked. One JSON line per instance in rows.jsonl
(written as instances finish; ``--resume`` skips finished ones). The RL side
is g8_g4_policy_curves.py; g9_g4_summary.py combines both.

``--methods`` and ``--processes`` allow re-timing a subset of the methods
(e.g. IGA and SA with fewer parallel processes on an otherwise idle machine).
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import logging
import time

from _common import checked_tardiness, parse_args, provenance, write_json

from fjsp_lab.maintenance.cpsat import CpSatError, solve_cpsat
from fjsp_lab.maintenance.generator import G4_GRID, g4_cases
from fjsp_lab.maintenance.metaheuristics import solve_metaheuristic
from fjsp_lab.maintenance.rules import solve_dispatch_rule

LOGGER = logging.getLogger(__name__)
BUDGETS = (0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)
SEARCH_SECONDS = 10.0
CPSAT = {'time_limit': 60.0, 'num_workers': 1, 'seed': 42}
SEED = 0
PROCESSES = 4
METHODS = ('EDD', 'MDD', 'ATC', 'IGA', 'GA', 'SA', 'CP-SAT')


def run_instance(job) -> dict:
    case, mode, cpsat_seconds, methods = job
    data = case.data
    row = {'case_id': case.case_id, 'mode': mode, 'num_tasks': case.num_tasks, 'num_machines': case.num_machines,
           'profile': case.profile, 'alpha_percent': case.alpha_percent, 'beta_percent': case.beta_percent,
           'tau_percent': case.tau_percent, 'instance_seed': case.instance_seed, 'windows': data.num_windows}
    for rule in ('EDD', 'MDD', 'ATC'):
        if rule not in methods:
            continue
        started = time.perf_counter()
        plan = solve_dispatch_rule(data, mode=mode, rule=rule)
        row[rule] = {'value': checked_tardiness(plan, data, mode), 'seconds': time.perf_counter() - started}
    for algorithm in ('IGA', 'GA'):
        if algorithm not in methods:
            continue
        outcome = solve_metaheuristic(data, mode=mode, algorithm=algorithm, evaluations=10**9, seed=SEED,
                                      time_limit=SEARCH_SECONDS)
        row[algorithm] = {'value': checked_tardiness(outcome.result, data, mode), 'decodes': outcome.evaluations,
                          'trace': [list(point) for point in outcome.trace]}
    if 'SA' in methods:
        row['SA'] = {}
    for budget in BUDGETS if 'SA' in methods else ():
        outcome = solve_metaheuristic(data, mode=mode, algorithm='SA', evaluations=10**9, seed=SEED,
                                      time_limit=budget)
        row['SA'][str(budget)] = {'value': checked_tardiness(outcome.result, data, mode),
                                  'decodes': outcome.evaluations}
    if 'CP-SAT' not in methods:
        return row
    trace = []
    try:
        result = solve_cpsat(data, mode=mode, time_limit=cpsat_seconds, num_workers=CPSAT['num_workers'],
                             seed=CPSAT['seed'], trace=trace)
        row['CP-SAT'] = {'value': checked_tardiness(result, data, mode), 'status': result.solver_status,
                         'bound': result.solver_objective_bound, 'trace': [list(point) for point in trace]}
    except CpSatError as exc:
        row['CP-SAT'] = {'value': None, 'status': 'NO_SCHEDULE', 'error': str(exc)[:300],
                         'trace': [list(point) for point in trace]}
    return row


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g7_g4_search_curves', resumable=True,
                      extra=lambda p: (p.add_argument('--limit', type=int, default=None, help='first N cases (smoke)'),
                                       p.add_argument('--cpsat-seconds', type=float, default=CPSAT['time_limit']),
                                       p.add_argument('--methods', nargs='+', default=list(METHODS), choices=METHODS),
                                       p.add_argument('--processes', type=int, default=PROCESSES)))
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)   # recorded at start: the code that actually runs
    path = args.output_dir / 'rows.jsonl'
    done = set()
    if path.exists():
        with open(path, encoding='utf-8') as handle:
            done = {(row['case_id'], row['mode']) for row in map(json.loads, handle)}
    jobs = [(case, mode, args.cpsat_seconds, tuple(args.methods)) for case in g4_cases()[:args.limit]
            for mode in ('fixed', 'joint') if (case.case_id, mode) not in done]
    LOGGER.info('%d instances to run (%d already done)', len(jobs), len(done))
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.processes) as pool, open(path, 'a', encoding='utf-8', newline='\n') as out:
        futures = [pool.submit(run_instance, job) for job in jobs]
        for count, future in enumerate(as_completed(futures), 1):
            out.write(json.dumps(future.result(), separators=(',', ':')) + '\n')
            out.flush()
            if count % 24 == 0:
                LOGGER.info('%d/%d (%.0f min)', count, len(jobs), (time.monotonic() - started) / 60)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g7_g4_search_curves', 'grid': G4_GRID, 'limit': args.limit, 'budgets': BUDGETS,
        'search_seconds': SEARCH_SECONDS, 'cpsat': {**CPSAT, 'time_limit': args.cpsat_seconds}, 'seed': SEED,
        'methods': args.methods, 'parallel_processes': args.processes, 'instances': len(done) + len(jobs),
        'elapsed_minutes_this_session': round((time.monotonic() - started) / 60, 1), **prov})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
