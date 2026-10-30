"""Rerun the G3A main and sensitivity grid (240 pairs, 480 solves) with solver_v2.

Inputs, order and solver settings are the exp_030 protocol's (1 s wall clock,
1 worker, seed 42); only result acceptance changes (see solver_v2). Every row
is kept, including failures. Pair definitions follow
reference_main_results.compare_pair. This is a fixed-vs-joint reference
comparison, not an RL comparison or thesis acceptance.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
import platform
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data, _solver_settings
from src.graduation.solver import GraduationSolverError
from src.graduation.solver_v2 import checked_metrics_v2, solve_parallel_maintenance_v2

LOGGER = logging.getLogger(__name__)
ORIGINAL_RAW = ROOT / 'experiments/results/exp_030_graduation_main_attempt2_v1/run/raw.csv'
ROW_FIELDS = ['sequence', 'case_id', 'group', 'mode', 'num_tasks', 'num_machines', 'alpha_percent',
              'beta_percent', 'tau_percent', 'instance_seed', 'fixed_policy', 'status', 'solver_status',
              'total_tardiness', 'solver_objective_value', 'solver_objective_bound', 'solver_gap',
              'solver_wall_time', 'makespan', 'error']
PAIR_FIELDS = ['case_id', 'group', 'num_tasks', 'num_machines', 'status', 'fixed_tardiness',
               'joint_tardiness', 'observed_difference', 'relative_improvement',
               'optimum_difference_lower', 'optimum_difference_upper', 'both_optimal', 'error']
SOURCES = ('src/graduation/solver_v2.py', 'src/graduation/solver.py', 'src/graduation/feasibility.py',
           'src/graduation/metrics.py', 'src/graduation/data.py',
           'src/graduation/reference_main_protocol.py', 'src/graduation/reference_protocol.py',
           'experiments/exp_035_graduation_main_v2.py')


def solve_row(sequence: int, case: dict, mode: str) -> tuple[dict, dict | None]:
    factors = case['factors']
    row = dict.fromkeys(ROW_FIELDS)
    row.update(sequence=sequence, case_id=case['case_id'], group=case['group'], mode=mode,
               num_tasks=factors['num_tasks'], num_machines=factors['num_machines'],
               alpha_percent=factors['alpha_percent'], beta_percent=factors['beta_percent'],
               tau_percent=factors['tau_percent'], instance_seed=factors['instance_seed'],
               fixed_policy=factors['fixed_policy'], error='')
    data = _data(case)
    try:
        result = solve_parallel_maintenance_v2(data, mode=mode, **_solver_settings())
        metrics = checked_metrics_v2(data, result, mode)
    except (GraduationSolverError, ValueError) as exc:
        no_schedule = type(exc) is GraduationSolverError and 'no accepted schedule' in str(exc)
        row.update(status='NO_SCHEDULE' if no_schedule else 'ERROR',
                   error=f'{type(exc).__name__}: {str(exc)[:300]}')
        return row, None
    row.update(status='ACCEPTED', **metrics)
    plan = {'records': [asdict(r) for r in result.records],
            'maintenance_records': [asdict(r) for r in result.maintenance_records]}
    return row, plan


def compare(case: dict, fixed: dict, joint: dict) -> dict:
    factors = case['factors']
    pair = dict.fromkeys(PAIR_FIELDS)
    pair.update(case_id=case['case_id'], group=case['group'], num_tasks=factors['num_tasks'],
                num_machines=factors['num_machines'], status='INCOMPLETE', both_optimal=False, error='')
    if fixed['status'] != 'ACCEPTED' or joint['status'] != 'ACCEPTED':
        pair['error'] = 'One or both rows have no accepted schedule'
        return pair
    fixed_t, joint_t = fixed['total_tardiness'], joint['total_tardiness']
    lower = max(0, fixed['solver_objective_bound'] - joint_t)
    upper = fixed_t - joint['solver_objective_bound']
    both_optimal = fixed['solver_status'] == joint['solver_status'] == 'OPTIMAL'
    pair.update(status='COMPLETE', fixed_tardiness=fixed_t, joint_tardiness=joint_t,
                observed_difference=fixed_t - joint_t,
                relative_improvement=None if fixed_t == 0 else (fixed_t - joint_t) / fixed_t,
                optimum_difference_lower=lower, optimum_difference_upper=upper, both_optimal=both_optimal)
    if both_optimal and joint_t > fixed_t:
        pair.update(status='INTEGRITY_ERROR', error='Proven joint optimum exceeds proven fixed optimum')
    elif upper < 0 or upper < lower:
        pair.update(status='INTEGRITY_ERROR', error='Solver bounds imply an impossible optimum-difference interval')
    return pair


def _group_summary(pairs: list[dict], rows: list[dict]) -> dict:
    complete = [p for p in pairs if p['status'] == 'COMPLETE']
    improvements = [p['relative_improvement'] for p in complete
                    if p['both_optimal'] and p['relative_improvement'] is not None]
    return {
        'planned_pairs': len(pairs), 'complete_pairs': len(complete),
        'both_optimal_pairs': sum(p['both_optimal'] for p in complete),
        'joint_lower': sum(p['observed_difference'] > 0 for p in complete),
        'ties': sum(p['observed_difference'] == 0 for p in complete),
        'joint_higher': sum(p['observed_difference'] < 0 for p in complete),
        'incomplete_pairs': sum(p['status'] == 'INCOMPLETE' for p in pairs),
        'integrity_errors': sum(p['status'] == 'INTEGRITY_ERROR' for p in pairs),
        'fixed_zero_pairs': sum(p['fixed_tardiness'] == 0 for p in complete),
        'positive_optimum_lower_bounds': sum(p['optimum_difference_lower'] > 0 for p in complete),
        'both_optimal_relative_improvement_mean': statistics.fmean(improvements) if improvements else None,
        'both_optimal_relative_improvement_median': statistics.median(improvements) if improvements else None,
        'optimal_runs': sum(r['solver_status'] == 'OPTIMAL' for r in rows),
        'feasible_runs': sum(r['solver_status'] == 'FEASIBLE' for r in rows),
        'objective_above_tardiness_runs': sum(
            r['status'] == 'ACCEPTED' and r['solver_objective_value'] > r['total_tardiness'] for r in rows),
    }


def summarize(cases: list[dict], rows: list[dict], pairs: list[dict]) -> dict:
    statuses = {s: sum(r['status'] == s for r in rows) for s in ('ACCEPTED', 'NO_SCHEDULE', 'ERROR')}
    groups = {}
    for group in ('primary', 'sensitivity'):
        keys = sorted({(c['factors']['num_tasks'], c['factors']['num_machines'])
                       for c in cases if c['group'] == group})
        for key in [None, *keys]:
            selected = [i for i, c in enumerate(cases) if c['group'] == group and (
                key is None or (c['factors']['num_tasks'], c['factors']['num_machines']) == key)]
            if not selected:
                continue
            name = group if key is None else f'{group}/n{key[0]}-m{key[1]}'
            groups[name] = _group_summary([pairs[i] for i in selected],
                                          [rows[2 * i + k] for i in selected for k in (0, 1)])
    return {'planned_pairs': len(cases), 'planned_calls': len(rows), 'status_counts': statuses,
            'groups': groups}


def compare_with_original(rows: list[dict]) -> dict:
    """Row-level agreement with exp_030 attempt 2 (1 s wall clock is not repeatable)."""
    if not ORIGINAL_RAW.exists():
        return {'available': False}
    with open(ORIGINAL_RAW, encoding='utf-8', newline='') as handle:
        original = {(r['case_id'], r['mode']): r for r in csv.DictReader(handle)}
    both = same = v2_better = v2_worse = recovered = 0
    for row in rows:
        old = original.get((row['case_id'], row['mode']))
        if old is None:
            continue
        if old['status'] == 'ERROR' and row['status'] == 'ACCEPTED':
            recovered += 1
        if old['status'] == 'ACCEPTED' and row['status'] == 'ACCEPTED':
            both += 1
            old_t = int(old['total_tardiness'])
            same += old_t == row['total_tardiness']
            v2_better += row['total_tardiness'] < old_t
            v2_worse += row['total_tardiness'] > old_t
    return {'available': True, 'both_accepted': both, 'same_tardiness': same,
            'v2_lower_tardiness': v2_better, 'v2_higher_tardiness': v2_worse,
            'original_errors_now_accepted': recovered}


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run_experiment(output_dir: Path, cases: list[dict] | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    cases = build_main_cases() if cases is None else cases
    rows, plans, pairs = [], {}, []
    for index, case in enumerate(cases):
        pair_rows = []
        for offset, mode in enumerate(('fixed', 'joint')):
            row, plan = solve_row(2 * index + offset, case, mode)
            rows.append(row)
            pair_rows.append(row)
            if plan is not None:
                plans[str(row['sequence'])] = plan
        pairs.append(compare(case, *pair_rows))
        if index % 20 == 19:
            LOGGER.info('%d/%d pairs solved', index + 1, len(cases))
    summary = summarize(cases, rows, pairs)
    failed = summary['status_counts']['ERROR'] + sum(g['integrity_errors'] for name, g in
                                                     summary['groups'].items() if '/' not in name)
    manifest = {
        'experiment': 'exp_035_graduation_main_v2',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'status': 'COMPLETED' if failed == 0 else 'FAILED',
        'research_status': 'not_achieved',
        'solver_settings': _solver_settings(),
        'summary': summary,
        'comparison_with_exp_030_attempt2': compare_with_original(rows),
        'environment': {
            'python': platform.python_version(), 'platform': platform.platform(),
            'ortools': importlib.metadata.version('ortools'),
            'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                         text=True, check=False).stdout.strip(),
        },
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    }
    _write_csv(output_dir / 'rows.csv', ROW_FIELDS, rows)
    _write_csv(output_dir / 'pairs.csv', PAIR_FIELDS, pairs)
    (output_dir / 'plans.json').write_text(json.dumps(plans, sort_keys=True) + '\n', encoding='utf-8')
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n',
                                              encoding='utf-8')
    LOGGER.info('%s: %s', manifest['status'], json.dumps(summary['status_counts']))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT / 'experiments' / 'runs' / 'exp_035_graduation_main_v2')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    return 0 if run_experiment(args.output_dir)['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
