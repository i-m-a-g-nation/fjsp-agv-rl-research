"""Check the upper-bound objective rule of solver_v2 on the G3A failure cases.

Part A reruns the 5 requests that failed the main batch (exp_030 attempt 2)
with the original solver and with solver_v2 under the batch settings.
Part B repeats solver_v2 twice with a deterministic time limit.
Part C compares solver_v2 with the exact enumeration oracle on the exp_021
tiny cases. This is a solver validation, not a G3 comparison.
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
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.exp_021_graduation_solver_check import build_cases as tiny_cases
from src.graduation.enumeration import enumerate_parallel_maintenance
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data
from src.graduation.solver import GraduationSolverError, solve_parallel_maintenance
from src.graduation.solver_v2 import checked_metrics_v2, solve_parallel_maintenance_v2

LOGGER = logging.getLogger(__name__)
BATCH_SETTINGS = {'time_limit': 1.0, 'num_workers': 1, 'seed': 42}
DETERMINISTIC_SETTINGS = {'time_limit': 30.0, 'num_workers': 1, 'seed': 42, 'max_deterministic_time': 0.3}
FAILED_REQUESTS = (
    ('g3a-main-n24-m2-a10-b25-t75-s404-midpoint', 'joint'),
    ('g3a-main-n24-m2-a10-b75-t75-s404-midpoint', 'fixed'),
    ('g3a-main-n24-m2-a30-b75-t75-s202-midpoint', 'fixed'),
    ('g3a-main-n24-m2-a30-b75-t75-s404-midpoint', 'fixed'),
    ('g3a-main-n24-m2-a30-b75-t75-s505-midpoint', 'joint'),
)
FIELDS = ['part', 'case_id', 'mode', 'solver', 'repeat', 'status', 'solver_status', 'objective',
          'bound', 'total_tardiness', 'objective_minus_tardiness', 'reference_total_tardiness',
          'wall_time', 'error']


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plan(result) -> dict:
    return {'records': [asdict(r) for r in result.records],
            'maintenance_records': [asdict(r) for r in result.maintenance_records]}


def _row(part, case_id, mode, solver_name, repeat, solve, data):
    row = dict.fromkeys(FIELDS)
    row.update(part=part, case_id=case_id, mode=mode, solver=solver_name, repeat=repeat, error='')
    try:
        result = solve(data, mode)
        if solver_name == 'v2':
            checked_metrics_v2(data, result, mode)
        row.update(status='ACCEPTED', solver_status=result.solver_status,
                   objective=result.solver_objective_value, bound=result.solver_objective_bound,
                   total_tardiness=result.total_tardiness,
                   objective_minus_tardiness=result.solver_objective_value - result.total_tardiness,
                   wall_time=round(result.solver_wall_time, 4))
        return row, _plan(result)
    except (GraduationSolverError, ValueError) as exc:
        row.update(status='ERROR', error=f'{type(exc).__name__}: {str(exc)[:300]}')
        return row, None


def run_experiment(output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    main_cases = {case['case_id']: case for case in build_main_cases()}
    rows, plans = [], {}

    def record(row, plan):
        rows.append(row)
        if plan is not None:
            plans[f"{row['part']}/{row['case_id']}/{row['mode']}/{row['solver']}/{row['repeat']}"] = plan

    for case_id, mode in FAILED_REQUESTS:
        data = _data(main_cases[case_id])
        record(*_row('A', case_id, mode, 'v1', 0,
                     lambda d, m: solve_parallel_maintenance(d, mode=m, **BATCH_SETTINGS), data))
        record(*_row('A', case_id, mode, 'v2', 0,
                     lambda d, m: solve_parallel_maintenance_v2(d, mode=m, **BATCH_SETTINGS), data))
        for repeat in (0, 1):
            record(*_row('B', case_id, mode, 'v2', repeat,
                         lambda d, m: solve_parallel_maintenance_v2(d, mode=m, **DETERMINISTIC_SETTINGS), data))
    for case in tiny_cases():
        for mode in ('fixed', 'joint'):
            row, plan = _row('C', case.name, mode, 'v2', 0,
                             lambda d, m: solve_parallel_maintenance_v2(d, mode=m, **BATCH_SETTINGS), case.data)
            row['reference_total_tardiness'] = enumerate_parallel_maintenance(case.data, mode=mode).total_tardiness
            record(row, plan)

    part_a_v2 = [r for r in rows if r['part'] == 'A' and r['solver'] == 'v2']
    part_b = [r for r in rows if r['part'] == 'B']
    part_c = [r for r in rows if r['part'] == 'C']
    repeat_identical = all(
        plans.get(f'B/{c}/{m}/v2/0') is not None
        and plans.get(f'B/{c}/{m}/v2/0') == plans.get(f'B/{c}/{m}/v2/1') for c, m in FAILED_REQUESTS)
    checks = {
        'part_a_v2_all_accepted': all(r['status'] == 'ACCEPTED' for r in part_a_v2),
        'part_b_all_accepted': all(r['status'] == 'ACCEPTED' for r in part_b),
        'part_b_repeats_identical': repeat_identical,
        'part_c_all_optimal_and_match_enumeration': all(
            r['status'] == 'ACCEPTED' and r['solver_status'] == 'OPTIMAL'
            and r['total_tardiness'] == r['reference_total_tardiness'] for r in part_c),
    }
    manifest = {
        'experiment': 'exp_034_graduation_solver_v2_check',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'status': 'PASSED' if all(checks.values()) else 'FAILED',
        'checks': checks,
        'part_a_v1_errors': sum(r['status'] == 'ERROR' for r in rows if r['part'] == 'A' and r['solver'] == 'v1'),
        'part_a_v2_objective_above_tardiness': sum(
            r['status'] == 'ACCEPTED' and r['objective_minus_tardiness'] > 0 for r in part_a_v2),
        'settings': {'A_and_C': BATCH_SETTINGS, 'B': DETERMINISTIC_SETTINGS},
        'rows': len(rows),
        'environment': {
            'python': platform.python_version(), 'platform': platform.platform(),
            'ortools': importlib.metadata.version('ortools'),
            'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                         text=True, check=False).stdout.strip(),
        },
        'source_sha256': {path: _sha_file(ROOT / path) for path in (
            'src/graduation/solver.py', 'src/graduation/solver_v2.py',
            'src/graduation/feasibility.py', 'src/graduation/enumeration.py',
            'experiments/exp_034_graduation_solver_v2_check.py')},
    }
    with open(output_dir / 'rows.csv', 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / 'plans.json').write_text(json.dumps(plans, sort_keys=True, indent=1) + '\n', encoding='utf-8')
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n',
                                              encoding='utf-8')
    LOGGER.info('%s: %s', manifest['status'], json.dumps(checks))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT / 'experiments' / 'runs' / 'exp_034_graduation_solver_v2_check')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    return 0 if run_experiment(args.output_dir)['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
