"""Graduation G3A: CP-SAT reference, fixed vs joint maintenance, on all 240 cases x 2 modes.

Short reference: 1 s wall clock, 1 worker, seed 42 for every instance.
With ``--long``: an additional 60 s, 4-worker reference for the n=24 primary
instances (run in parallel processes; multi-worker CP-SAT is not
bit-reproducible, so plans and bounds are archived).

Per pair the observed difference T_fixed - T_joint is reported together with
the interval for the difference of the optima implied by the solver bounds;
only both-OPTIMAL pairs prove a difference. Writes rows.csv, pairs.csv,
plans.json and manifest.json.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import logging
import statistics

from _common import parse_args, provenance, write_csv, write_json

from fjsp_lab.maintenance import check_parallel_maintenance_feasibility
from fjsp_lab.maintenance.cpsat import CpSatError, solve_cpsat
from fjsp_lab.maintenance.generator import g3a_cases

LOGGER = logging.getLogger(__name__)
SHORT = {'time_limit': 1.0, 'num_workers': 1, 'seed': 42}
LONG = {'time_limit': 60.0, 'num_workers': 4, 'seed': 42, 'processes': 4}
FACTORS = ('case_id', 'group', 'num_tasks', 'num_machines', 'alpha_percent', 'beta_percent', 'tau_percent',
           'instance_seed', 'fixed_policy')


def solve(job) -> tuple[dict, dict | None]:
    case, mode, settings, label = job
    row = {**{f: getattr(case, f) for f in FACTORS}, 'mode': mode, 'setting': label}
    try:
        result = solve_cpsat(case.data, mode=mode, time_limit=settings['time_limit'],
                             num_workers=settings['num_workers'], seed=settings['seed'])
    except CpSatError as exc:
        row.update(status='NO_SCHEDULE', error=str(exc)[:300])
        return row, None
    accepted, issues = check_parallel_maintenance_feasibility(result, case.data, mode=mode)
    if not accepted:
        raise ValueError(f'{case.case_id}/{mode}: checker rejected a CP-SAT plan: {issues}')
    row.update(status='ACCEPTED', solver_status=result.solver_status, total_tardiness=result.total_tardiness,
               objective=result.solver_objective_value, bound=result.solver_objective_bound,
               gap=result.solver_gap, wall_time=result.solver_wall_time, makespan=result.makespan)
    plan = {'records': [asdict(r) for r in result.records],
            'maintenance_records': [asdict(r) for r in result.maintenance_records]}
    return row, plan


def compare(fixed: dict, joint: dict) -> dict:
    pair = {f: fixed[f] for f in FACTORS}
    if fixed['status'] != 'ACCEPTED' or joint['status'] != 'ACCEPTED':
        return {**pair, 'status': 'INCOMPLETE'}
    tf, tj = fixed['total_tardiness'], joint['total_tardiness']
    lower, upper = max(0, fixed['bound'] - tj), tf - joint['bound']
    both = fixed['solver_status'] == joint['solver_status'] == 'OPTIMAL'
    if both and tj > tf:
        raise ValueError(f'{pair["case_id"]}: proven joint optimum exceeds proven fixed optimum')
    return {**pair, 'status': 'COMPLETE', 'fixed_tardiness': tf, 'joint_tardiness': tj, 'observed_difference': tf - tj,
            'relative_improvement': (tf - tj) / tf if tf else None, 'optimum_difference_lower': lower,
            'optimum_difference_upper': upper, 'both_optimal': both}


def summarize(pairs: list[dict]) -> dict:
    out = {}
    keys = sorted({(p['group'], p['num_tasks'], p['num_machines'], p['fixed_policy']) for p in pairs})
    for group, n, m, policy in keys:
        chosen = [p for p in pairs if (p['group'], p['num_tasks'], p['num_machines'], p['fixed_policy']) == (group, n, m, policy)
                  and p['status'] == 'COMPLETE']
        positive = [p for p in chosen if p['fixed_tardiness'] > 0]
        out[f'{group}/n{n}-m{m}/{policy}'] = {
            'pairs': len(chosen), 'both_optimal': sum(p['both_optimal'] for p in chosen),
            'joint_lower': sum(p['observed_difference'] > 0 for p in chosen),
            'ties': sum(p['observed_difference'] == 0 for p in chosen),
            'joint_higher': sum(p['observed_difference'] < 0 for p in chosen),
            'fixed_zero': sum(p['fixed_tardiness'] == 0 for p in chosen),
            'proven_positive_difference': sum(p['optimum_difference_lower'] > 0 for p in chosen),
            'mean_relative_improvement_where_fixed_positive':
                statistics.fmean(p['relative_improvement'] for p in positive) if positive else None,
            'median_relative_improvement_where_fixed_positive':
                statistics.median(p['relative_improvement'] for p in positive) if positive else None,
        }
    return out


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g1_cpsat_fixed_vs_joint',
                      lambda p: p.add_argument('--long', action='store_true', help='add the 60 s n=24 reference'))
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    cases = g3a_cases()
    rows, plans = [], {}
    for index, case in enumerate(cases):
        for mode in ('fixed', 'joint'):
            row, plan = solve((case, mode, SHORT, 'cp_sat_1s'))
            rows.append(row)
            plans[f'{case.case_id}/{mode}/cp_sat_1s'] = plan
        if index % 40 == 39:
            LOGGER.info('%d/%d cases', index + 1, len(cases))
    pairs = [compare(rows[2 * i], rows[2 * i + 1]) for i in range(len(cases))]
    if args.long:
        jobs = [(c, mode, LONG, 'cp_sat_60s') for c in cases if c.group == 'primary' and c.num_tasks == 24
                for mode in ('fixed', 'joint')]
        LOGGER.info('long reference: %d solves', len(jobs))
        with ProcessPoolExecutor(max_workers=LONG['processes']) as pool:
            for (case, mode, _, label), (row, plan) in zip(jobs, pool.map(solve, jobs)):
                rows.append(row)
                plans[f'{case.case_id}/{mode}/{label}'] = plan
    write_csv(args.output_dir / 'rows.csv', rows)
    write_csv(args.output_dir / 'pairs.csv', pairs)
    write_json(args.output_dir / 'plans.json', plans)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g1_cpsat_fixed_vs_joint', 'short_setting': SHORT, 'long_setting': LONG if args.long else None,
        'solves': len(rows), 'accepted': sum(r['status'] == 'ACCEPTED' for r in rows),
        'complete_pairs': sum(p['status'] == 'COMPLETE' for p in pairs), 'summary': summarize(pairs),
        **provenance(__file__)})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
