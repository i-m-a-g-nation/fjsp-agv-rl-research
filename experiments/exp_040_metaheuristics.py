"""GA / SA / improved GA vs rules, the learned policy and CP-SAT on the G3A grid.

Protocol fixed before the full run:
* instances: the 480 G3A instances of exp_038 (primary 160 pairs +
  sensitivity 80 pairs, fixed and joint);
* algorithms GA, SA, IGA with the default settings in
  ``src/graduation/metaheuristics.py`` (no tuning); budgets of 1 000, 10 000
  and 50 000 decodes; seeds 0-4 for every (instance, algorithm, budget);
* the only pilot looked at budget scale on 20 primary n=24 instances
  (seed 0); no parameter was changed after it;
* rules, policy and CP-SAT values come from the archived exp_038 rows;
* every plan is G1-checked inside the solver; a value below a proven
  CP-SAT optimum stops the run.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
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

from experiments.exp_037_sampling_decoding import paired
from src.graduation.metaheuristics import ALGORITHMS, DEFAULT_SETTINGS, solve_metaheuristic
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data

LOGGER = logging.getLogger(__name__)
G3_RAW = ROOT / 'experiments/results/exp_038_g3b_comparison_v1/rows.csv'
PROTOCOL = {
    'instances': 'G3A grid of exp_038: 240 pairs x fixed/joint',
    'algorithms': list(ALGORITHMS),
    'settings': DEFAULT_SETTINGS,
    'budgets': [1000, 10000, 50000],
    'seeds': [0, 1, 2, 3, 4],
    'parallel_processes': 4,
    'reference_rows': 'exp_038_g3b_comparison_v1/rows.csv (rules, policy_s0, CP-SAT 1 s / 60 s)',
    'headline_comparisons': {
        'IGA_10000 vs policy_s0_r9': 'similar wall time (about 80 ms)',
        'IGA vs GA / SA': 'same budget; IGA = GA + heuristic seeds + local search',
        'IGA_50000 vs cp_sat_60s': 'n=24 primary instances',
    },
}
ARCHIVED = ('EDD', 'MDD', 'ATC', 'best_of_3_rules', 'best_of_9_rules',
            'policy_s0_r1', 'policy_s0_r3', 'policy_s0_r9', 'cp_sat_1s')
FACTORS = ('num_tasks', 'num_machines', 'alpha_percent', 'beta_percent', 'tau_percent')
SOURCES = ('src/graduation/metaheuristics.py', 'experiments/exp_040_metaheuristics.py')


def run_instance(job: tuple[dict, str, dict]) -> dict:
    """Worker: all algorithms, budgets and seeds on one instance."""
    case, mode, protocol = job
    data = _data(case)
    out = {'case_id': case['case_id'], 'mode': mode}
    for algorithm in protocol['algorithms']:
        for budget in protocol['budgets']:
            values, seconds = [], []
            for seed in protocol['seeds']:
                started = time.perf_counter()
                outcome = solve_metaheuristic(data, mode=mode, algorithm=algorithm, evaluations=budget, seed=seed)
                seconds.append(time.perf_counter() - started)
                values.append(outcome.result.total_tardiness)
            name = f'{algorithm}_{budget}'
            out[name] = statistics.fmean(values)
            out[f'{name}_best'] = min(values)
            out[f'{name}_worst'] = max(values)
            out[f'{name}_seconds'] = statistics.fmean(seconds)
    return out


def _gain(fixed: float, joint: float) -> float | None:
    return (fixed - joint) / fixed if fixed > 0 else None


def joint_gain(rows: list[dict]) -> dict:
    """Fixed-vs-joint reduction of the best known value, overall and by factor."""
    pairs = {}
    for row in rows:
        pairs.setdefault(row['case_id'], {})[row['mode']] = row
    items = [(p['fixed'], p['joint']) for p in pairs.values()]

    def describe(selected):
        gains = [g for g in (_gain(f['best_known'], j['best_known']) for f, j in selected) if g is not None]
        return {'pairs': len(selected), 'pairs_with_positive_fixed': len(gains),
                'mean_fixed': statistics.fmean(f['best_known'] for f, _ in selected),
                'mean_joint': statistics.fmean(j['best_known'] for _, j in selected),
                'mean_relative_reduction': statistics.fmean(gains) if gains else None,
                'joint_better': sum(j['best_known'] < f['best_known'] for f, j in selected),
                'joint_worse': sum(j['best_known'] > f['best_known'] for f, j in selected),
                'both_proven_optimal': sum(f['best_known_proven_optimal'] and j['best_known_proven_optimal']
                                           for f, j in selected)}

    out = {'all': describe(items)}
    for group in sorted({f['group'] for f, _ in items}):
        for n in sorted({f['num_tasks'] for f, _ in items}):
            chosen = [(f, j) for f, j in items if f['group'] == group and f['num_tasks'] == n]
            if not chosen:
                continue
            out[f'{group}/n{n}'] = describe(chosen)
            for factor in ('num_machines', 'alpha_percent', 'beta_percent', 'tau_percent', 'fixed_policy'):
                for level in sorted({f[factor] for f, _ in chosen}):
                    out[f'{group}/n{n}/{factor}={level}'] = describe([(f, j) for f, j in chosen if f[factor] == level])
    return out


def summarize(rows: list[dict], protocol: dict) -> dict:
    meta = [f'{a}_{b}' for a in protocol['algorithms'] for b in protocol['budgets']]
    methods = [*ARCHIVED, 'cp_sat_60s', *meta]
    groups = {'all': rows}
    for key in sorted({(r['group'], r['num_tasks'], r['num_machines']) for r in rows}):
        groups[f'{key[0]}/n{key[1]}-m{key[2]}'] = [r for r in rows if (r['group'], r['num_tasks'], r['num_machines']) == key]
    top = protocol['budgets'][-1]
    out = {}
    for name, selected in groups.items():
        present = [m for m in methods if all(r.get(m) is not None for r in selected)]
        comparisons = []
        for budget in protocol['budgets']:
            comparisons += [paired(selected, f'IGA_{budget}', f'GA_{budget}'),
                            paired(selected, f'IGA_{budget}', f'SA_{budget}'),
                            paired(selected, f'IGA_{budget}', 'policy_s0_r9'),
                            paired(selected, f'IGA_{budget}', 'best_of_9_rules')]
        comparisons.append(paired(selected, 'policy_s0_r1', f'IGA_{protocol["budgets"][0]}'))
        if 'cp_sat_60s' in present:
            comparisons += [paired(selected, f'{a}_{top}', 'cp_sat_60s') for a in protocol['algorithms']]
        out[name] = {
            'instances': len(selected),
            'mean': {m: statistics.fmean(r[m] for r in selected) for m in present},
            'mean_gap_to_best_known': {m: statistics.fmean(r[m] - r['best_known'] for r in selected) for m in present},
            'best_known_hits': {m: sum(r[m] == r['best_known'] for r in selected) for m in present},
            'mean_seconds': {m: statistics.fmean(r[f'{m}_seconds'] for r in selected) for m in meta},
            'mean_seed_spread': {m: statistics.fmean(r[f'{m}_worst'] - r[f'{m}_best'] for r in selected) for m in meta},
            'paired': comparisons,
        }
    return out


def build_rows(cases: list[dict], results: list[dict], protocol: dict) -> list[dict]:
    with open(G3_RAW, encoding='utf-8', newline='') as handle:
        archived = {(r['case_id'], r['mode']): r for r in csv.DictReader(handle)}
    case_by_id = {c['case_id']: c for c in cases}
    rows = []
    for result in results:
        old = archived[(result['case_id'], result['mode'])]
        case = case_by_id[result['case_id']]
        row = {'case_id': result['case_id'], 'group': case['group'], 'mode': result['mode'],
               **{f: case['factors'][f] for f in FACTORS}, 'fixed_policy': case['factors']['fixed_policy'],
               **{c: int(old[c]) for c in ARCHIVED},
               'cp_sat_60s': int(old['cp_sat_60s']) if old['cp_sat_60s'] else None,
               'cp_sat_1s_status': old['cp_sat_1s_status'], 'cp_sat_60s_status': old['cp_sat_60s_status'] or None,
               'best_known_exp_038': int(old['best_known']),
               'best_known_proven_optimal': old['best_known_proven_optimal'] == 'True'}
        row.update({k: v for k, v in result.items() if k not in ('case_id', 'mode')})
        meta_best = min(result[f'{a}_{b}_best'] for a in protocol['algorithms'] for b in protocol['budgets'])
        if row['best_known_proven_optimal'] and meta_best < row['best_known_exp_038']:
            raise ValueError(f'{row["case_id"]}/{row["mode"]}: metaheuristic {meta_best} beats a proven optimum')
        row['best_known'] = min(row['best_known_exp_038'], meta_best)
        rows.append(row)
    return rows


def run_experiment(output_dir: Path, protocol: dict = PROTOCOL, cases: list[dict] | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    cases = build_main_cases() if cases is None else cases
    jobs = [(case, mode, protocol) for case in cases for mode in ('fixed', 'joint')]
    LOGGER.info('metaheuristics: %d instances', len(jobs))
    with ProcessPoolExecutor(max_workers=protocol['parallel_processes']) as pool:
        results = list(pool.map(run_instance, jobs))
    rows = build_rows(cases, results, protocol)
    manifest = {
        'experiment': 'exp_040_metaheuristics',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'protocol': protocol,
        'instances': len(rows),
        'runs': len(rows) * len(protocol['algorithms']) * len(protocol['budgets']) * len(protocol['seeds']),
        'new_best_known': sum(r['best_known'] < r['best_known_exp_038'] for r in rows),
        'summary': summarize(rows, protocol),
        'joint_gain': joint_gain(rows),
        'all_plans_g1_checked': True,
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'research_status': 'not_achieved',
        'environment': {
            'python': platform.python_version(), 'platform': platform.platform(),
            'scipy': importlib.metadata.version('scipy'),
            'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                         text=True, check=False).stdout.strip(),
        },
        'archived_input_sha256': {'experiments/results/exp_038_g3b_comparison_v1/rows.csv':
                                  hashlib.sha256(G3_RAW.read_bytes()).hexdigest()},
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    }
    with open(output_dir / 'rows.csv', 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n',
                                              encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'experiments' / 'runs' / 'exp_040_metaheuristics')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    manifest = run_experiment(args.output_dir)
    LOGGER.info('done: %d runs, %d new best-known, %.1f s', manifest['runs'], manifest['new_best_known'],
                manifest['elapsed_seconds'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
