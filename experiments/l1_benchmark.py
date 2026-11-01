"""Innovation project L1: FJSPT benchmark alignment and the effect of blocking and buffer capacity.

Data: the 10 Deroussi & Norre instances, their published reference
solutions and the 8-machine layout, read from the ignored local folder
``instances/external/FJSPT`` (no redistribution licence; see
docs/models/logistics_model_zh.md, section 5). Their SHA-256 is recorded in
the manifest. 2 vehicles, no return to L/U, no extra handling time.

Configurations (questions fixed before the run):

* ``bench``: benchmark conventions (no blocking, unlimited buffers).
  Q1: does replaying each reference solution give its reported makespan and
  pass the checker? Q2: how does the CP-SAT result compare with it?
* ``block-inf``, ``block-2``, ``block-1``, ``block-0``: post-processing
  blocking with input buffer capacity unlimited / 2 / 1 / 0.
  Q3: how much do blocking and smaller buffers raise the CP-SAT makespan
  (relative to ``bench``)? Q4: how often do the non-delay rules deadlock,
  and how far are the schedules they do return from CP-SAT?
  Q5 (exploratory, n = 10 only): joint EFT against the best decoupled rule.

Methods per instance and configuration: CP-SAT (60 s, 8 workers, seed 0;
multi-worker runs are not bit-reproducible, so status, bound and schedule
are archived), the rules EFT, FIFO+NV, SPT+NV, MWKR+NV, and RANDOM with seeds
0-9. Every returned schedule is re-checked here. Writes rows.csv,
summary.csv, schedules.json and manifest.json.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import statistics
import time

from _common import ROOT, parse_args, provenance, sha256, write_csv, write_json

from fjsp_lab.logistics import check_logistics_feasibility, load_fjspt
from fjsp_lab.logistics.cpsat import LogisticsCpSatError, solve_cpsat
from fjsp_lab.logistics.rules import solve_rule
from fjsp_lab.logistics.sequences import decode_sequences, parse_reference_solution
from fjsp_lab.logistics.simulator import SimulationDeadlock

CONFIGS = {'bench': (False, None), 'block-inf': (True, None), 'block-2': (True, 2),
           'block-1': (True, 1), 'block-0': (True, 0)}               # name: (blocking, buffer capacity)
CPSAT = {'time_limit': 60.0, 'num_workers': 8, 'seed': 0}
RULES = ('EFT', 'FIFO+NV', 'SPT+NV', 'MWKR+NV')
RANDOM_SEEDS = range(10)


def checked(plan, data) -> int:
    accepted, issues = check_logistics_feasibility(plan, data)
    if not accepted:
        raise ValueError(f'Checker rejected a returned schedule: {issues}')
    return plan.makespan


def schedule_record(plan) -> dict:
    return {'production': [asdict(r) for r in plan.production.records],
            'transports': [asdict(t) for t in plan.transports]}


def main() -> None:
    args = parse_args(__doc__.splitlines()[0], 'l1_benchmark',
                      lambda p: p.add_argument('--data-dir', type=Path, default=ROOT / 'instances/external/FJSPT'))
    data_dir = args.data_dir
    layout = data_dir / 'DeroussiNorre_layout.txt'
    if not layout.is_file():
        raise SystemExit(f'Benchmark data missing in {data_dir}; see docs/models/logistics_model_zh.md section 5')
    inputs = [layout] + [data_dir / folder / f'fjsp{i}.txt' for folder in ('DeroussiNorre', 'Deroussi') for i in range(1, 11)]
    manifest = {'experiment': 'l1_benchmark', 'configs': {k: {'blocking': b, 'buffer': c} for k, (b, c) in CONFIGS.items()},
                'cpsat': CPSAT, 'rules': list(RULES), 'random_seeds': list(RANDOM_SEEDS),
                'inputs_sha256': {p.relative_to(data_dir).as_posix(): sha256(p) for p in inputs},
                'provenance': provenance(__file__)}
    rows, schedules = [], {}
    for i in range(1, 11):
        name = f'fjsp{i}'
        for config, (blocking, buffer) in CONFIGS.items():
            data = load_fjspt(data_dir / 'DeroussiNorre' / f'{name}.txt', layout, blocking=blocking,
                              buffer_capacity=buffer)
            base = {'instance': name, 'config': config, 'blocking': blocking,
                    'buffer': 'inf' if buffer is None else buffer}
            if config == 'bench':
                machines, vehicles, reported = parse_reference_solution(
                    (data_dir / 'Deroussi' / f'{name}.txt').read_text(encoding='utf-8'), data)
                replay = decode_sequences(data, machines, vehicles)
                rows.append({**base, 'method': 'reference-replay', 'status': 'ACCEPTED',
                             'makespan': checked(replay, data), 'reported': reported})
            try:
                plan = solve_cpsat(data, **CPSAT)
                rows.append({**base, 'method': 'CP-SAT', 'status': plan.solver_status, 'makespan': checked(plan, data),
                             'bound': plan.solver_objective_bound, 'seconds': round(plan.solver_wall_time, 3)})
                schedules[f'{name}/{config}'] = schedule_record(plan)
            except LogisticsCpSatError as exc:
                rows.append({**base, 'method': 'CP-SAT', 'status': 'NO_SCHEDULE', 'error': str(exc)[:200]})
            for rule, seed in [(r, 0) for r in RULES] + [('RANDOM', s) for s in RANDOM_SEEDS]:
                label = rule if rule != 'RANDOM' else f'RANDOM-s{seed}'
                started = time.perf_counter()
                try:
                    makespan, status = checked(solve_rule(data, rule, seed=seed), data), 'ACCEPTED'
                except SimulationDeadlock:
                    makespan, status = '', 'DEADLOCK'
                rows.append({**base, 'method': label, 'status': status, 'makespan': makespan,
                             'seconds': round(time.perf_counter() - started, 4)})
            print(name, config, 'done', flush=True)
    write_csv(args.output_dir / 'rows.csv', rows)
    write_json(args.output_dir / 'schedules.json', schedules)
    write_json(args.output_dir / 'manifest.json', manifest)
    write_csv(args.output_dir / 'summary.csv', summarize(rows))


def summarize(rows: list[dict]) -> list[dict]:
    """Per configuration and method: deadlocks, mean gap to CP-SAT on returned schedules, CP-SAT optimality.

    The RANDOM seeds are pooled into one row (n = 10 instances x 10 seeds).
    """
    def family(method: str) -> str:
        return 'RANDOM' if method.startswith('RANDOM-s') else method

    cpsat = {(r['instance'], r['config']): r['makespan'] for r in rows if r['method'] == 'CP-SAT' and 'makespan' in r}
    bench = {name: value for (name, config), value in cpsat.items() if config == 'bench'}
    summary = []
    for config in CONFIGS:
        methods = dict.fromkeys(family(r['method']) for r in rows if r['config'] == config)
        for method in methods:
            group = [r for r in rows if r['config'] == config and family(r['method']) == method]
            done = [r for r in group if r['status'] in ('ACCEPTED', 'OPTIMAL', 'FEASIBLE')]
            gaps = [(r['makespan'] - cpsat[r['instance'], config]) / cpsat[r['instance'], config]
                    for r in done if method != 'CP-SAT' and (r['instance'], config) in cpsat]
            item = {'config': config, 'method': method, 'n': len(group), 'returned': len(done),
                    'deadlocks': sum(r['status'] == 'DEADLOCK' for r in group),
                    'mean_makespan': round(statistics.fmean(r['makespan'] for r in done), 3) if done else '',
                    'mean_gap_to_cpsat': round(statistics.fmean(gaps), 4) if gaps else ''}
            if method == 'CP-SAT':
                item['optimal'] = sum(r['status'] == 'OPTIMAL' for r in group)
                increases = [(r['makespan'] - bench[r['instance']]) / bench[r['instance']]
                             for r in done if r['instance'] in bench]
                item['mean_increase_vs_bench'] = round(statistics.fmean(increases), 4) if increases else ''
            summary.append(item)
    return summary


if __name__ == '__main__':
    main()
