"""Innovation project L1: cost of decoupling (machines first, then vehicles) against joint CP-SAT.

Same 10 Deroussi & Norre instances and 5 configurations as ``l1_benchmark``
(benchmark conventions; blocking with input buffers inf / 2 / 1 / 0), read
from the ignored local folder ``instances/external/FJSPT``.

Methods (``fjsp_lab.logistics.decoupled``), each with the joint CP-SAT's
total budget of 60 s on 8 workers, seed 0, split 30 s + 30 s:

* D0: stage 1 pure FJSP (transport ignored), stage 2 vehicles and times;
* D1: stage 1 with loaded travel times as gaps (vehicles assumed always
  available, no blocking or buffers), stage 2 as D0.

The joint CP-SAT results are read from the archived run
``experiments/results/l1_benchmark`` (same budget; its commit is recorded).

Questions fixed before the run:

* Q1: coordination gap = (decoupled - joint) / joint per configuration, for
  D0 and D1 (reported with the joint solver's bound where it is not optimal);
* Q2: is the gap larger with blocking and small buffers than under the
  benchmark conventions? (descriptive; 10 instances)
* Q3: how often is the stage 1 plan not executable at all (stage 2 proves
  infeasibility)?

Every returned schedule is re-checked here. Writes rows.csv, summary.csv and
manifest.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import statistics

from _common import ROOT, parse_args, provenance, read_csv, sha256, write_csv, write_json

from fjsp_lab.logistics import check_logistics_feasibility, load_fjspt
from fjsp_lab.logistics.cpsat import LogisticsCpSatError
from fjsp_lab.logistics.decoupled import DecoupledPlanInfeasible, solve_decoupled

CONFIGS = {'bench': (False, None), 'block-inf': (True, None), 'block-2': (True, 2),
           'block-1': (True, 1), 'block-0': (True, 0)}               # name: (blocking, buffer capacity)
BUDGET = {'time_limit': 60.0, 'num_workers': 8, 'seed': 0}
VARIANTS = {'D0': False, 'D1': True}                               # name: stage 1 uses transport lags
JOINT_RUN = ROOT / 'experiments/results/l1_benchmark'


def main() -> None:
    args = parse_args(__doc__.splitlines()[0], 'l1_decoupled',
                      lambda p: p.add_argument('--data-dir', type=Path, default=ROOT / 'instances/external/FJSPT'))
    layout = args.data_dir / 'DeroussiNorre_layout.txt'
    if not layout.is_file():
        raise SystemExit(f'Benchmark data missing in {args.data_dir}; see docs/models/logistics_model_zh.md section 5')
    joint_manifest = json.loads((JOINT_RUN / 'manifest.json').read_text(encoding='utf-8'))
    joint = {(r['instance'], r['config']): r for r in read_csv(JOINT_RUN / 'rows.csv') if r['method'] == 'CP-SAT'}
    inputs = [layout] + [args.data_dir / 'DeroussiNorre' / f'fjsp{i}.txt' for i in range(1, 11)]
    manifest = {'experiment': 'l1_decoupled', 'budget': BUDGET, 'variants': VARIANTS,
                'configs': {k: {'blocking': b, 'buffer': c} for k, (b, c) in CONFIGS.items()},
                'joint_reference': {'run': 'experiments/results/l1_benchmark',
                                    'git_commit': joint_manifest['provenance']['git_commit'],
                                    'rows_sha256': sha256(JOINT_RUN / 'rows.csv')},
                'inputs_sha256': {p.relative_to(args.data_dir).as_posix(): sha256(p) for p in inputs},
                'provenance': provenance(__file__)}
    rows = []
    for i in range(1, 11):
        name = f'fjsp{i}'
        for config, (blocking, buffer) in CONFIGS.items():
            data = load_fjspt(args.data_dir / 'DeroussiNorre' / f'{name}.txt', layout, blocking=blocking,
                              buffer_capacity=buffer)
            ref = joint[name, config]
            base = {'instance': name, 'config': config, 'joint_makespan': int(ref['makespan']),
                    'joint_status': ref['status'], 'joint_bound': float(ref['bound'])}
            for variant, lags in VARIANTS.items():
                row = {**base, 'method': variant}
                try:
                    schedule, plan = solve_decoupled(data, transport_lags=lags, **BUDGET)
                    accepted, issues = check_logistics_feasibility(schedule, data)
                    if not accepted:
                        raise ValueError(f'Checker rejected a returned schedule: {issues}')
                    row.update(status=schedule.solver_status, makespan=schedule.makespan,
                               stage1_status=plan.status, stage1_estimate=plan.estimate,
                               gap=round((schedule.makespan - base['joint_makespan']) / base['joint_makespan'], 4))
                except DecoupledPlanInfeasible:
                    row.update(status='PLAN_INFEASIBLE')
                except LogisticsCpSatError as exc:
                    row.update(status=f'NO_SCHEDULE:{exc.status}')
                rows.append(row)
            print(name, config, 'done', flush=True)
    write_csv(args.output_dir / 'rows.csv', rows)
    write_json(args.output_dir / 'manifest.json', manifest)
    write_csv(args.output_dir / 'summary.csv', summarize(rows))


def summarize(rows: list[dict]) -> list[dict]:
    """Per configuration and variant: executable plans, mean gap to joint, wins/ties of joint."""
    summary = []
    for config in CONFIGS:
        for variant in VARIANTS:
            group = [r for r in rows if r['config'] == config and r['method'] == variant]
            done = [r for r in group if 'makespan' in r]
            summary.append({
                'config': config, 'method': variant, 'n': len(group), 'executable': len(done),
                'plan_infeasible': sum(r['status'] == 'PLAN_INFEASIBLE' for r in group),
                'mean_gap_to_joint': round(statistics.fmean(r['gap'] for r in done), 4) if done else '',
                'max_gap_to_joint': max((r['gap'] for r in done), default=''),
                'joint_better': sum(r['makespan'] > r['joint_makespan'] for r in done),
                'equal': sum(r['makespan'] == r['joint_makespan'] for r in done),
                'decoupled_better': sum(r['makespan'] < r['joint_makespan'] for r in done)})
    return summary


if __name__ == '__main__':
    main()
