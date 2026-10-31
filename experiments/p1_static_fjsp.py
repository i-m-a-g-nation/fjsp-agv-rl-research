"""Phase 1: dispatching rules and CP-SAT on the toy instance and the 30 tracked FJSPLib files.

Every schedule is re-checked by the static feasibility checker. CP-SAT runs
once per instance (1 worker, seed 42, time limit below); only OPTIMAL is
reported as optimal, FEASIBLE is a time-limited incumbent. FJSPLib bounds
come from instances/fjsplib_bks.csv. Writes rows.csv, toy_gantt.png and
manifest.json.
"""

from __future__ import annotations

import logging
import time

from _common import ROOT, parse_args, provenance, read_csv, write_csv, write_json

from fjsp_lab.fjsp import RULES, check_feasibility, create_toy_instance, load_project_benchmark_file, solve_rule
from fjsp_lab.fjsp.cpsat import CpSatError, solve_cpsat
from fjsp_lab.fjsp.gantt import plot_gantt

LOGGER = logging.getLogger(__name__)


def run(instance, name: str, bounds: dict, time_limit: float) -> list[dict]:
    rows = []
    lb, ub = bounds.get(name, (None, None))
    methods = [(rule, lambda r=rule: solve_rule(instance, r)) for rule in RULES]
    methods.append(('CP-SAT', lambda: solve_cpsat(instance, time_limit=time_limit, num_workers=1, seed=42)))
    for method, solve in methods:
        row = {'instance': name, 'jobs': instance.num_jobs, 'machines': instance.num_machines,
               'operations': instance.total_ops, 'method': method, 'fjsplib_lb': lb, 'fjsplib_ub': ub}
        started = time.perf_counter()
        try:
            result = solve()
            feasible, violations = check_feasibility(result, expected_instance=instance)
            if not feasible:
                raise RuntimeError(f'checker rejected a returned schedule: {violations}')
            row.update(makespan=result.makespan, feasible=True, status=result.solver_status or 'HEURISTIC',
                       bound=result.solver_objective_bound,
                       gap_to_ub=None if ub is None else (result.makespan - ub) / ub)
        except CpSatError as exc:
            row.update(makespan=None, feasible=False, status='NO_SCHEDULE', error=str(exc)[:300])
        row['seconds'] = round(time.perf_counter() - started, 4)
        rows.append(row)
    return rows


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'p1_static_fjsp',
                      lambda p: p.add_argument('--time-limit', type=float, default=10.0))
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)   # recorded at start: the code that actually runs
    bounds = {r['instance_name']: (int(r['fjsplib_lb']), int(r['fjsplib_ub']))
              for r in read_csv(ROOT / 'instances/fjsplib_bks.csv')}
    toy = create_toy_instance()
    rows = run(toy, 'toy_3x3', bounds, args.time_limit)
    plot_gantt(solve_cpsat(toy, time_limit=args.time_limit), title='toy 3x3, CP-SAT',
               save_path=args.output_dir / 'toy_gantt.png')
    for path in sorted((ROOT / 'instances/fjsplib').rglob('*.fjs')):
        name = path.relative_to(ROOT / 'instances/fjsplib').as_posix()
        rows += run(load_project_benchmark_file(path), name, bounds, args.time_limit)
        LOGGER.info('%s: %s', name, {r['method']: r['makespan'] for r in rows[-len(RULES) - 1:]})
    write_csv(args.output_dir / 'rows.csv', rows)
    cp = [r for r in rows if r['method'] == 'CP-SAT']
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'p1_static_fjsp', 'time_limit': args.time_limit, 'instances': len(cp),
        'schedules': len(rows), 'all_feasible': all(r['feasible'] for r in rows),
        'cpsat_status': {s: sum(r['status'] == s for r in cp) for s in ('OPTIMAL', 'FEASIBLE', 'NO_SCHEDULE')},
        'cpsat_matches_fjsplib_ub': sum(r['makespan'] == r['fjsplib_ub'] for r in cp if r['fjsplib_ub'] is not None),
        **prov})
    return 0 if all(r['feasible'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
