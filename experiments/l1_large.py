"""Innovation project L1: deadlocks and buffer effects on larger instances, with lookahead avoidance.

Instances: Brandimarte mk01, mk02, mk03, mk04, mk05, mk07 (in the repository)
with the integer layouts of Homayouni & Fontes for 4, 5, 6 and 8 machines
(L/U at location 0), read from the ignored local folder
``instances/external/HomayouniFontes`` (no redistribution licence; hashed in
the manifest). mk06, mk08-mk10 are left out: their 10- and 15-machine layouts
contain non-integer times. 2 vehicles, no return to L/U. The vehicle count is
our choice, so values are not comparable with Homayouni & Fontes' results.

Configurations as in ``l1_benchmark``: benchmark conventions (no blocking,
unlimited buffers) and blocking with input buffers inf / 2 / 1 / 0.

Methods: the rules EFT, FIFO+NV, SPT+NV, MWKR+NV and RANDOM (seeds 0-9),
each plain (non-delay; may deadlock) and with lookahead deadlock avoidance
(``avoid_deadlock=True``). CP-SAT is not run: a probe showed that from 55
operations on it finds no schedule within 60 s once blocking and finite
buffers are on. Gaps are measured against an instance lower bound that uses
no solver: the largest of (a) the longest single-job route with its trips,
(b) the total minimum processing time divided by the number of machines and
(c) the total minimum loaded travel of all jobs divided by the number of
vehicles (empty trips ignored).

Questions fixed before the run:

* Q1: how often do the plain rules deadlock, per configuration?
* Q2: does avoidance return a schedule in every case?
* Q3: how much do blocking and small buffers raise the best avoided-rule
  makespan per instance, relative to the benchmark conventions?
  (heuristic results, not optima)
* Q4 (exploratory): joint EFT against the decoupled rules, with avoidance.

Every returned schedule is re-checked here. Writes rows.csv, summary.csv
and manifest.json.
"""

from __future__ import annotations

from pathlib import Path
import statistics
import time

from _common import ROOT, parse_args, provenance, sha256, write_csv, write_json

from fjsp_lab.fjsp import load_project_benchmark_file
from fjsp_lab.logistics import LogisticsInstance, check_logistics_feasibility, parse_layout
from fjsp_lab.logistics.rules import solve_rule
from fjsp_lab.logistics.simulator import SimulationDeadlock

INSTANCES = ('mk01', 'mk02', 'mk03', 'mk04', 'mk05', 'mk07')
CONFIGS = {'bench': (False, None), 'block-inf': (True, None), 'block-2': (True, 2),
           'block-1': (True, 1), 'block-0': (True, 0)}               # name: (blocking, buffer capacity)
RULES = ('EFT', 'FIFO+NV', 'SPT+NV', 'MWKR+NV')
RANDOM_SEEDS = range(10)
VEHICLES = 2


def lower_bound(data: LogisticsInstance) -> int:
    """max(longest job alone incl. trips, min processing / machines, min loaded travel / vehicles); no solver."""
    route = travel = 0
    for job in data.production.jobs:
        moving = {data.lu: 0}                        # least loaded travel to reach each machine for this job
        for op in job.operations:
            moving = {machine: min(c + (0 if here == machine else data.loaded_time(here, machine))
                                   for here, c in moving.items()) for machine, _ in op.machine_options}
        if data.return_to_lu:
            moving = {data.lu: min(c + data.loaded_time(here, data.lu) for here, c in moving.items())}
        travel += min(moving.values())
        cost = {data.lu: 0}
        for op in job.operations:
            cost = {machine: min(c + (0 if here == machine else data.loaded_time(here, machine))
                                 for here, c in cost.items()) + p for machine, p in op.machine_options}
        if data.return_to_lu:
            cost = {data.lu: min(c + data.loaded_time(here, data.lu) for here, c in cost.items())}
        route = max(route, min(cost.values()))
    work = sum(min(p for _, p in op.machine_options) for job in data.production.jobs for op in job.operations)
    return max(route, -(-work // data.num_machines), -(-travel // data.num_vehicles))


def main() -> None:
    args = parse_args(__doc__.splitlines()[0], 'l1_large',
                      lambda p: p.add_argument('--data-dir', type=Path, default=ROOT / 'instances/external/HomayouniFontes'))
    productions = {name: load_project_benchmark_file(ROOT / f'instances/fjsplib/Brandimarte1993/{name}.fjs')
                   for name in INSTANCES}
    layouts = {k: args.data_dir / f'layout_{k}M.txt' for k in sorted({p.num_machines for p in productions.values()})}
    if not all(path.is_file() for path in layouts.values()):
        raise SystemExit(f'Layouts missing in {args.data_dir}; see docs/models/logistics_model_zh.md')
    manifest = {'experiment': 'l1_large', 'instances': list(INSTANCES), 'vehicles': VEHICLES,
                'configs': {k: {'blocking': b, 'buffer': c} for k, (b, c) in CONFIGS.items()},
                'rules': list(RULES), 'random_seeds': list(RANDOM_SEEDS),
                'inputs_sha256': {p.name: sha256(p) for p in layouts.values()},
                'provenance': provenance(__file__)}
    rows = []
    for name, production in productions.items():
        travel = parse_layout(layouts[production.num_machines].read_text(encoding='utf-8'), production.num_machines)
        for config, (blocking, buffer) in CONFIGS.items():
            data = LogisticsInstance.create(production, travel, num_vehicles=VEHICLES, buffer_capacity=buffer,
                                            blocking=blocking, return_to_lu=False)
            base = {'instance': name, 'operations': production.total_ops, 'machines': production.num_machines,
                    'config': config, 'lower_bound': lower_bound(data)}
            for rule, seed in [(r, 0) for r in RULES] + [('RANDOM', s) for s in RANDOM_SEEDS]:
                label = rule if rule != 'RANDOM' else f'RANDOM-s{seed}'
                for avoid in (False, True):
                    started = time.perf_counter()
                    try:
                        plan = solve_rule(data, rule, seed=seed, avoid_deadlock=avoid)
                        accepted, issues = check_logistics_feasibility(plan, data)
                        if not accepted:
                            raise ValueError(f'Checker rejected a returned schedule: {issues}')
                        status, makespan = 'ACCEPTED', plan.makespan
                    except SimulationDeadlock:
                        status, makespan = 'DEADLOCK', ''
                    rows.append({**base, 'method': label, 'avoid_deadlock': avoid, 'status': status,
                                 'makespan': makespan, 'seconds': round(time.perf_counter() - started, 3)})
            print(name, config, 'done', flush=True)
    write_csv(args.output_dir / 'rows.csv', rows)
    write_json(args.output_dir / 'manifest.json', manifest)
    write_csv(args.output_dir / 'summary.csv', summarize(rows))


def summarize(rows: list[dict]) -> list[dict]:
    """Per configuration, method family and mode: deadlocks, mean gap to the lower bound, and the buffer effect."""
    def family(method: str) -> str:
        return 'RANDOM' if method.startswith('RANDOM-s') else method

    best = {}                                     # best avoided-rule makespan per (instance, config)
    for r in rows:
        if r['avoid_deadlock'] and r['status'] == 'ACCEPTED':
            key = (r['instance'], r['config'])
            best[key] = min(best.get(key, r['makespan']), r['makespan'])
    summary = []
    for config in CONFIGS:
        for method in dict.fromkeys(family(r['method']) for r in rows):
            for avoid in (False, True):
                group = [r for r in rows if r['config'] == config and family(r['method']) == method
                         and r['avoid_deadlock'] == avoid]
                done = [r for r in group if r['status'] == 'ACCEPTED']
                summary.append({'config': config, 'method': method, 'avoid_deadlock': avoid, 'n': len(group),
                                'deadlocks': len(group) - len(done),
                                'mean_gap_to_lower_bound': round(statistics.fmean(
                                    (r['makespan'] - r['lower_bound']) / r['lower_bound'] for r in done), 4) if done else ''})
        increases = [(best[n, config] - best[n, 'bench']) / best[n, 'bench']
                     for n in INSTANCES if (n, config) in best and (n, 'bench') in best]
        summary.append({'config': config, 'method': 'BEST-AVOIDED', 'avoid_deadlock': True, 'n': len(increases),
                        'mean_increase_vs_bench': round(statistics.fmean(increases), 4) if increases else '',
                        'max_increase_vs_bench': round(max(increases), 4) if increases else ''})
    return summary


if __name__ == '__main__':
    main()
