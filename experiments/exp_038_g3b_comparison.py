"""G3B: scoring policy vs dispatch rules vs CP-SAT on the G3A grid (480 instances).

Protocol fixed before the run:
* instances: all 240 G3A pairs (primary + sensitivity) x fixed/joint; never
  used for training or checkpoint selection;
* final model: the exp_036 seed with the lowest validation mean (selected
  before this run); the other seeds are reported only for variance;
* policy at 1/3/9 rollouts, rules EDD/MDD/ATC, best of 3, 9-rule portfolio;
* CP-SAT: exp_035 rows (1 s, 1 worker) for all instances, plus a stronger
  reference for every n=24 primary instance (60 s, 4 workers, seed 42,
  solver_v2), run in parallel processes; multi-worker CP-SAT is not
  bit-reproducible, so its status, bound and plan are archived.
Every plan is G1-checked.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
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
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scipy.stats import wilcoxon

from experiments.exp_037_sampling_decoding import CHECKPOINT_DIR, evaluate, load_policies
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data
from src.graduation.scoring_training import Instance
from src.graduation.solver import GraduationSolverError
from src.graduation.solver_v2 import checked_metrics_v2, solve_parallel_maintenance_v2

LOGGER = logging.getLogger(__name__)
CP_SHORT_RAW = ROOT / 'experiments/results/exp_035_graduation_main_v2_v1/rows.csv'
PROTOCOL = {
    'instances': 'G3A main grid: 240 pairs (primary 160 + sensitivity 80) x fixed/joint',
    'final_model_rule': 'exp_036 checkpoint with the lowest validation mean greedy tardiness',
    'policy_rollouts': {'r1': 0, 'r3': 2, 'r9': 8},
    'cp_sat_short': 'exp_035 rows: 1 s, 1 worker, seed 42, solver_v2',
    'cp_sat_long': {'scope': 'primary n=24', 'time_limit': 60.0, 'num_workers': 4, 'seed': 42,
                    'parallel_processes': 4},
}
FACTORS = ('seed', 'num_tasks', 'num_machines', 'alpha_percent', 'beta_percent', 'tau_percent', 'mode')
SOURCES = ('src/graduation/dispatch_rules.py', 'src/graduation/action_features.py',
           'src/graduation/scoring_policy.py', 'src/graduation/solver_v2.py',
           'experiments/exp_037_sampling_decoding.py', 'experiments/exp_038_g3b_comparison.py')


def final_model_name() -> str:
    manifest = json.loads((CHECKPOINT_DIR / 'manifest.json').read_text(encoding='utf-8'))
    selected = manifest['selected_checkpoints']
    return min(sorted(selected), key=lambda name: selected[name]['val_mean_tardiness'])


def solve_long(job: tuple[dict, str, dict]) -> dict:
    """Worker: one strong CP-SAT reference solve; failures are returned, not raised."""
    case, mode, settings = job
    row = {'case_id': case['case_id'], 'mode': mode, 'status': 'ERROR', 'solver_status': None,
           'total_tardiness': None, 'solver_objective_value': None, 'solver_objective_bound': None,
           'solver_wall_time': None, 'plan': None, 'error': ''}
    data = _data(case)
    try:
        result = solve_parallel_maintenance_v2(data, mode=mode, time_limit=settings['time_limit'],
                                               num_workers=settings['num_workers'], seed=settings['seed'])
        metrics = checked_metrics_v2(data, result, mode)
    except (GraduationSolverError, ValueError) as exc:
        row['error'] = f'{type(exc).__name__}: {str(exc)[:300]}'
        return row
    row.update(status='ACCEPTED', solver_status=metrics['solver_status'],
               total_tardiness=metrics['total_tardiness'],
               solver_objective_value=metrics['solver_objective_value'],
               solver_objective_bound=metrics['solver_objective_bound'],
               solver_wall_time=metrics['solver_wall_time'],
               plan={'records': [asdict(r) for r in result.records],
                     'maintenance_records': [asdict(r) for r in result.maintenance_records]})
    return row


def g3_instances(cases: list[dict]) -> tuple[list[Instance], list[tuple[str, str, str]]]:
    instances, keys = [], []
    for case in cases:
        f = case['factors']
        for mode in ('fixed', 'joint'):
            instances.append(Instance(_data(case), mode, f['num_tasks'], f['num_machines'], f['alpha_percent'],
                                      f['beta_percent'], f['tau_percent'], f['instance_seed']))
            keys.append((case['case_id'], case['group'], mode))
    return instances, keys


def paired(rows: list[dict], method: str, baseline: str) -> dict:
    diffs = [row[method] - row[baseline] for row in rows]
    nonzero = [d for d in diffs if d != 0]
    base_mean = statistics.fmean(row[baseline] for row in rows)
    return {'method': method, 'baseline': baseline, 'n': len(rows),
            'mean_difference': statistics.fmean(diffs),
            'relative_difference': statistics.fmean(diffs) / base_mean if base_mean else None,
            'wins': sum(d < 0 for d in diffs), 'ties': sum(d == 0 for d in diffs),
            'losses': sum(d > 0 for d in diffs),
            'wilcoxon_p_nonzero': float(wilcoxon(nonzero).pvalue) if len(nonzero) >= 10 else None}


def summarize(rows: list[dict], methods: list[str], final: str) -> dict:
    groups = {'all': rows}
    for key in sorted({(r['group'], r['num_tasks'], r['num_machines']) for r in rows}):
        groups[f'{key[0]}/n{key[1]}-m{key[2]}'] = [r for r in rows if (r['group'], r['num_tasks'], r['num_machines']) == key]
    for mode in ('fixed', 'joint'):
        groups[f'mode/{mode}'] = [r for r in rows if r['mode'] == mode]
    out = {}
    for name, selected in groups.items():
        present = [m for m in methods if all(r.get(m) is not None for r in selected)]
        positive = [r for r in selected if r['best_known'] > 0]
        out[name] = {
            'instances': len(selected),
            'mean': {m: statistics.fmean(r[m] for r in selected) for m in present},
            'mean_gap_to_best_known': {m: statistics.fmean(r[m] - r['best_known'] for r in selected) for m in present},
            'mean_relative_gap_where_best_known_positive': {
                m: statistics.fmean((r[m] - r['best_known']) / r['best_known'] for r in positive) if positive else None
                for m in present},
            'best_known_hits': {m: sum(r[m] == r['best_known'] for r in selected) for m in present},
            'paired_final_model': [paired(selected, f'{final}_r{b}', base)
                                   for b, base in (('1', 'MDD'), ('3', 'best_of_3_rules'), ('9', 'best_of_9_rules'),
                                                   ('1', 'cp_sat_1s'), ('3', 'cp_sat_1s'))]
                                  + ([paired(selected, f'{final}_r{b}', 'cp_sat_60s') for b in ('1', '3', '9')]
                                     if 'cp_sat_60s' in present else []),
        }
    return out


def run_experiment(output_dir: Path, protocol: dict = PROTOCOL, cases: list[dict] | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    cases = build_main_cases() if cases is None else cases
    long_settings = protocol['cp_sat_long']
    jobs = [(case, mode, long_settings) for case in cases if case['group'] == 'primary'
            and case['factors']['num_tasks'] == 24 for mode in ('fixed', 'joint')]
    LOGGER.info('CP-SAT long references: %d solves', len(jobs))
    with ProcessPoolExecutor(max_workers=long_settings['parallel_processes']) as pool:
        long_rows = list(pool.map(solve_long, jobs))
    long_by_key = {(r['case_id'], r['mode']): r for r in long_rows}
    cp_long_seconds = time.monotonic() - started

    with open(CP_SHORT_RAW, encoding='utf-8', newline='') as handle:
        short = {(r['case_id'], r['mode']): r for r in csv.DictReader(handle)}
    policies = load_policies()
    final = final_model_name()
    instances, keys = g3_instances(cases)
    rows, seconds = evaluate(instances, policies)
    for row, (case_id, group, mode) in zip(rows, keys):
        ref = short[(case_id, mode)]
        if ref['status'] != 'ACCEPTED':
            raise ValueError(f'exp_035 row {case_id}/{mode} is not accepted')
        row.update(case_id=case_id, group=group, cp_sat_1s=int(ref['total_tardiness']),
                   cp_sat_1s_status=ref['solver_status'])
        strong = long_by_key.get((case_id, mode))
        accepted = strong is not None and strong['status'] == 'ACCEPTED'
        row['cp_sat_60s'] = strong['total_tardiness'] if accepted else None
        row['cp_sat_60s_status'] = strong['solver_status'] if accepted else None
        row['cp_sat_60s_bound'] = strong['solver_objective_bound'] if accepted else None
        candidates = [v for k, v in row.items() if k not in FACTORS and isinstance(v, int)
                      and k not in ('cp_sat_60s_bound',)]
        row['best_known'] = min(candidates)
        proven = row['cp_sat_1s_status'] == 'OPTIMAL' or row['cp_sat_60s_status'] == 'OPTIMAL'
        row['best_known_proven_optimal'] = proven
    methods = ['EDD', 'MDD', 'ATC', 'best_of_3_rules', 'best_of_9_rules',
               *[f'{name}_r{b}' for name in policies for b in ('1', '3', '9')], 'cp_sat_1s', 'cp_sat_60s']
    manifest = {
        'experiment': 'exp_038_g3b_comparison',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'protocol': protocol,
        'final_model': final,
        'instances': len(rows),
        'cp_sat_long': {
            'solves': len(long_rows),
            'status_counts': {s: sum(r['status'] == s for r in long_rows) for s in ('ACCEPTED', 'ERROR')},
            'solver_status_counts': {s: sum(r['solver_status'] == s for r in long_rows) for s in ('OPTIMAL', 'FEASIBLE')},
            'wall_seconds_total': round(cp_long_seconds, 1),
        },
        'heuristic_seconds_per_instance': seconds,
        'summary': summarize(rows, methods, final),
        'all_plans_g1_checked': True,
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'research_status': 'not_achieved',
        'environment': {
            'python': platform.python_version(), 'platform': platform.platform(),
            'ortools': importlib.metadata.version('ortools'), 'numpy': importlib.metadata.version('numpy'),
            'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                         text=True, check=False).stdout.strip(),
        },
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    }
    with open(output_dir / 'rows.csv', 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / 'cp_sat_60s.json').write_text(json.dumps(long_rows, sort_keys=True) + '\n', encoding='utf-8')
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n',
                                              encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'experiments' / 'runs' / 'exp_038_g3b_comparison')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    manifest = run_experiment(args.output_dir)
    LOGGER.info('done: final model %s, CP long %s', manifest['final_model'], json.dumps(manifest['cp_sat_long']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
