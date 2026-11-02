"""Innovation project L1: SA / GA reference search on the small benchmark and on the larger instances.

Part A (quality check): the 10 Deroussi & Norre instances, 5 configurations
(benchmark conventions; blocking with input buffers inf / 2 / 1 / 0), SA and
GA with 5000 decodings, seeds 0 and 1, against the archived CP-SAT results of
``l1_benchmark`` (optimal on 41 of 50 instance-configurations).

Part B (larger instances): Brandimarte mk01-05/mk07 with the Homayouni &
Fontes layouts as in ``l1_large``, SA with 1000 decodings, seeds 0 and 1,
against the archived best avoided rule of ``l1_large`` and the same
solver-free lower bound.

Data: the ignored local folders ``instances/external/FJSPT`` and
``instances/external/HomayouniFontes`` (hashed in the manifest). Runs are
independent and seeded; they are spread over 8 processes, so the recorded
seconds are for information only (no timing claims).

Questions fixed before the run:

* Q1: how far are SA and GA from the CP-SAT result on the small instances,
  per configuration (only OPTIMAL cases are gaps to an optimum)?
* Q2: how much does SA improve on the best avoided rule on the larger
  instances, per configuration?
* Q3: with SA as reference, how much do blocking and small buffers raise
  the makespan on the larger instances relative to the benchmark
  conventions (compare with the rule-based estimate of l1_large)?
* Q4: how often does decoding fall back to the priority decoder or fail?

Every returned schedule is re-checked here. Writes rows.csv, summary.csv
and manifest.json.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import statistics
import time

from _common import ROOT, parse_args, provenance, read_csv, sha256, write_csv, write_json

from fjsp_lab.fjsp import load_project_benchmark_file
from fjsp_lab.logistics import LogisticsInstance, check_logistics_feasibility, load_fjspt, parse_layout
from fjsp_lab.logistics.metaheuristics import solve_ga, solve_sa
from l1_large import INSTANCES as LARGE, lower_bound

CONFIGS = {'bench': (False, None), 'block-inf': (True, None), 'block-2': (True, 2),
           'block-1': (True, 1), 'block-0': (True, 0)}               # name: (blocking, buffer capacity)
SMALL = {'evaluations': 5000, 'seeds': (0, 1), 'methods': ('SA', 'GA')}
LARGE_RUN = {'evaluations': 1000, 'seeds': (0, 1), 'methods': ('SA',)}
SOLVERS = {'SA': solve_sa, 'GA': solve_ga}
PROCESSES = 8


def build(job: tuple) -> LogisticsInstance:
    part, name, config, dirs = job[:4]
    blocking, buffer = CONFIGS[config]
    if part == 'small':
        base = Path(dirs['small'])
        return load_fjspt(base / 'DeroussiNorre' / f'{name}.txt', base / 'DeroussiNorre_layout.txt',
                          blocking=blocking, buffer_capacity=buffer)
    production = load_project_benchmark_file(ROOT / f'instances/fjsplib/Brandimarte1993/{name}.fjs')
    layout = Path(dirs['large']) / f'layout_{production.num_machines}M.txt'
    travel = parse_layout(layout.read_text(encoding='utf-8'), production.num_machines)
    return LogisticsInstance.create(production, travel, num_vehicles=2, buffer_capacity=buffer,
                                    blocking=blocking, return_to_lu=False)


def run(job: tuple) -> dict:
    part, name, config, dirs, method, seed, evaluations = job
    data = build(job)
    started = time.perf_counter()
    outcome = SOLVERS[method](data, evaluations=evaluations, seed=seed)
    accepted, issues = check_logistics_feasibility(outcome.schedule, data)
    if not accepted:
        raise ValueError(f'{part}/{name}/{config}/{method}/{seed}: checker rejected the schedule: {issues}')
    return {'part': part, 'instance': name, 'config': config, 'method': method, 'seed': seed,
            'evaluations': outcome.evaluations, 'makespan': outcome.schedule.makespan,
            'start_makespan': outcome.trace[0][1], 'fallbacks': outcome.fallback_decodings,
            'infeasible': outcome.infeasible_decodings, 'lower_bound': lower_bound(data) if part == 'large' else '',
            'seconds': round(time.perf_counter() - started, 1)}


def main() -> None:
    args = parse_args(__doc__.splitlines()[0], 'l1_search', lambda p: (
        p.add_argument('--small-dir', type=Path, default=ROOT / 'instances/external/FJSPT'),
        p.add_argument('--large-dir', type=Path, default=ROOT / 'instances/external/HomayouniFontes')))
    dirs = {'small': str(args.small_dir), 'large': str(args.large_dir)}
    benchmark_rows = ROOT / 'experiments/results/l1_benchmark/rows.csv'
    large_rows = ROOT / 'experiments/results/l1_large/rows.csv'
    inputs = [args.small_dir / 'DeroussiNorre_layout.txt'] + \
        [args.small_dir / 'DeroussiNorre' / f'fjsp{i}.txt' for i in range(1, 11)] + \
        sorted(args.large_dir.glob('layout_*M.txt'))
    manifest = {'experiment': 'l1_search', 'small': SMALL, 'large': LARGE_RUN, 'processes': PROCESSES,
                'configs': {k: {'blocking': b, 'buffer': c} for k, (b, c) in CONFIGS.items()},
                'references_sha256': {'l1_benchmark/rows.csv': sha256(benchmark_rows),
                                      'l1_large/rows.csv': sha256(large_rows)},
                'inputs_sha256': {p.name if p.parent.name != 'DeroussiNorre' else f'DeroussiNorre/{p.name}': sha256(p)
                                  for p in inputs},
                'provenance': provenance(__file__)}
    jobs = [('small', f'fjsp{i}', config, dirs, method, seed, SMALL['evaluations'])
            for i in range(1, 11) for config in CONFIGS for method in SMALL['methods'] for seed in SMALL['seeds']]
    jobs += [('large', name, config, dirs, method, seed, LARGE_RUN['evaluations'])
             for name in LARGE for config in CONFIGS for method in LARGE_RUN['methods'] for seed in LARGE_RUN['seeds']]
    jobs.sort(key=lambda job: (job[0] != 'large', job[2] in ('bench', 'block-inf')))   # slow ones first
    rows = []
    with ProcessPoolExecutor(max_workers=PROCESSES) as pool:
        for row in pool.map(run, jobs):
            rows.append(row)
            print(row['part'], row['instance'], row['config'], row['method'], row['seed'], row['makespan'], flush=True)
    rows.sort(key=lambda r: (r['part'], r['instance'], list(CONFIGS).index(r['config']), r['method'], r['seed']))
    write_csv(args.output_dir / 'rows.csv', rows)
    write_json(args.output_dir / 'manifest.json', manifest)
    write_csv(args.output_dir / 'summary.csv', summarize(rows, read_csv(benchmark_rows), read_csv(large_rows)))


def summarize(rows: list[dict], benchmark: list[dict], large: list[dict]) -> list[dict]:
    """Gaps to the references, per part, configuration and method (seeds pooled)."""
    cpsat = {(r['instance'], r['config']): (int(r['makespan']), r['status'])
             for r in benchmark if r['method'] == 'CP-SAT' and r['makespan']}
    best_rule = {}
    for r in large:
        if r['avoid_deadlock'] == 'True' and r['status'] == 'ACCEPTED':
            key = (r['instance'], r['config'])
            best_rule[key] = min(best_rule.get(key, int(r['makespan'])), int(r['makespan']))
    summary = []
    for config in CONFIGS:
        for method in SMALL['methods']:
            group = [r for r in rows if r['part'] == 'small' and r['config'] == config and r['method'] == method]
            optimal = [r for r in group if cpsat[r['instance'], config][1] == 'OPTIMAL']
            summary.append({'part': 'small', 'config': config, 'method': method, 'runs': len(group),
                            'mean_gap_to_cpsat': round(statistics.fmean(
                                (r['makespan'] - cpsat[r['instance'], config][0]) / cpsat[r['instance'], config][0]
                                for r in group), 4),
                            'runs_on_optimal': len(optimal),
                            'mean_gap_to_optimum': round(statistics.fmean(
                                (r['makespan'] - cpsat[r['instance'], config][0]) / cpsat[r['instance'], config][0]
                                for r in optimal), 4) if optimal else '',
                            'fallback_share': round(sum(r['fallbacks'] for r in group)
                                                    / sum(r['evaluations'] for r in group), 4),
                            'infeasible': sum(r['infeasible'] for r in group)})
        group = [r for r in rows if r['part'] == 'large' and r['config'] == config]
        best = {}
        for r in group:
            best[r['instance']] = min(best.get(r['instance'], r['makespan']), r['makespan'])
        bench_best = {}
        for r in rows:
            if r['part'] == 'large' and r['config'] == 'bench':
                bench_best[r['instance']] = min(bench_best.get(r['instance'], r['makespan']), r['makespan'])
        summary.append({'part': 'large', 'config': config, 'method': 'SA', 'runs': len(group),
                        'mean_change_vs_best_rule': round(statistics.fmean(
                            (r['makespan'] - best_rule[r['instance'], config]) / best_rule[r['instance'], config]
                            for r in group), 4),
                        'mean_gap_to_lower_bound': round(statistics.fmean(
                            (r['makespan'] - r['lower_bound']) / r['lower_bound'] for r in group), 4),
                        'mean_increase_vs_bench_best_of_seeds': round(statistics.fmean(
                            (best[n] - bench_best[n]) / bench_best[n] for n in best), 4),
                        'fallback_share': round(sum(r['fallbacks'] for r in group)
                                                / sum(r['evaluations'] for r in group), 4),
                        'infeasible': sum(r['infeasible'] for r in group)})
    return summary


if __name__ == '__main__':
    main()
