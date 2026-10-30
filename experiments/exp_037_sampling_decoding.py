"""Compute-matched comparison of exp_036 policies with sampling decoding vs rules.

No training: the three exp_036 checkpoints (hash-checked) are reused. On a
new, untouched test split (seeds 40000-40599, 100 per size) each method is
compared with rules at the same number of complete rollouts:

* 1 rollout:  greedy policy           vs MDD (best single rule on exp_036 test)
* 3 rollouts: greedy + 2 samples      vs best of EDD/MDD/ATC
* 9 rollouts: greedy + 8 samples      vs best of the 9-rule portfolio

K values follow from compute matching, not tuning. Every plan is G1-checked.
"""

from __future__ import annotations

import argparse
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

from scipy.stats import wilcoxon

from src.graduation.dispatch_rules import RULE_PORTFOLIO, solve_dispatch_rule
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data
from src.graduation.scoring_policy import ScoringPolicy, best_of_rollouts
from src.graduation.scoring_training import Instance, make_instances

LOGGER = logging.getLogger(__name__)
CHECKPOINT_DIR = ROOT / 'experiments/results/exp_036_scoring_policy_v1'
EXTERNAL_RAW = ROOT / 'experiments/results/exp_035_graduation_main_v2_v1/rows.csv'
PROTOCOL = {
    'test': {'seeds': [40000, 40600], 'sampler_seed': 4, 'balanced': True},
    'checkpoints': 'exp_036_scoring_policy_v1 policy_s0/s1/s2 (hash-checked)',
    'sampling_seed': 0,
    'budgets': {'1': {'policy_samples': 0, 'baseline': 'MDD'},
                '3': {'policy_samples': 2, 'baseline': 'best_of_EDD_MDD_ATC'},
                '9': {'policy_samples': 8, 'baseline': 'best_of_9_rule_portfolio'}},
    'rule_portfolio': [list(item) for item in RULE_PORTFOLIO],
}
SOURCES = ('src/graduation/dispatch_rules.py', 'src/graduation/action_features.py',
           'src/graduation/scoring_policy.py', 'src/graduation/scoring_training.py',
           'experiments/exp_037_sampling_decoding.py')


def load_policies() -> dict[str, ScoringPolicy]:
    manifest = json.loads((CHECKPOINT_DIR / 'manifest.json').read_text(encoding='utf-8'))
    return {name: ScoringPolicy.load(CHECKPOINT_DIR / 'checkpoints' / f'{name}.npz', expected_sha256=digest)
            for name, digest in sorted(manifest['checkpoint_sha256'].items())}


def _checked(result, instance: Instance) -> int:
    accepted, issues = check_parallel_maintenance_feasibility(result, instance.data, mode=instance.mode)
    if not accepted:
        raise ValueError(f'G1 rejected a plan: {issues}')
    return result.total_tardiness


def evaluate(instances: list[Instance], policies: dict, protocol: dict = PROTOCOL) -> tuple[list[dict], dict]:
    rows, seconds = [], {}

    def timed(name, function):
        started = time.perf_counter()
        value = function()
        seconds[name] = seconds.get(name, 0.0) + time.perf_counter() - started
        return value

    for instance in instances:
        row = {'seed': instance.seed, 'num_tasks': instance.num_tasks, 'num_machines': instance.num_machines,
               'alpha_percent': instance.alpha_percent, 'beta_percent': instance.beta_percent,
               'tau_percent': instance.tau_percent, 'mode': instance.mode}
        portfolio = {}
        for rule, k in RULE_PORTFOLIO:
            label = rule if rule != 'ATC' else f'ATC_k{k:g}'
            portfolio[label] = timed('rules', lambda: _checked(
                solve_dispatch_rule(instance.data, mode=instance.mode, rule=rule, atc_k=k), instance))
        row.update(EDD=portfolio['EDD'], MDD=portfolio['MDD'], ATC=portfolio['ATC_k1'])
        row['best_of_3_rules'] = min(row['EDD'], row['MDD'], row['ATC'])
        row['best_of_9_rules'] = min(portfolio.values())
        for name, policy in policies.items():
            for budget, spec in protocol['budgets'].items():
                row[f'{name}_r{budget}'] = timed(f'policy_r{budget}', lambda: _checked(best_of_rollouts(
                    policy, instance.data, mode=instance.mode, samples=spec['policy_samples'],
                    seed=protocol['sampling_seed']), instance))
        rows.append(row)
    return rows, {name: value / len(instances) for name, value in seconds.items()}


BASELINE_COLUMN = {'1': 'MDD', '3': 'best_of_3_rules', '9': 'best_of_9_rules'}


def paired(rows: list[dict], method: str, baseline: str) -> dict:
    diffs = [row[method] - row[baseline] for row in rows]
    nonzero = [d for d in diffs if d != 0]
    base_mean = statistics.fmean(row[baseline] for row in rows)
    return {'method': method, 'baseline': baseline, 'n': len(rows),
            'method_mean': statistics.fmean(row[method] for row in rows), 'baseline_mean': base_mean,
            'mean_difference': statistics.fmean(diffs),
            'relative_difference': statistics.fmean(diffs) / base_mean if base_mean else None,
            'wins': sum(d < 0 for d in diffs), 'ties': sum(d == 0 for d in diffs),
            'losses': sum(d > 0 for d in diffs),
            'wilcoxon_p_nonzero': float(wilcoxon(nonzero).pvalue) if len(nonzero) >= 10 else None}


def summarize(rows: list[dict], policy_names: list[str]) -> dict:
    groups = {'all': rows}
    for n, m in sorted({(r['num_tasks'], r['num_machines']) for r in rows}):
        groups[f'n{n}-m{m}'] = [r for r in rows if (r['num_tasks'], r['num_machines']) == (n, m)]
    columns = [c for c in rows[0] if c not in ('seed', 'num_tasks', 'num_machines', 'alpha_percent',
                                               'beta_percent', 'tau_percent', 'mode')]
    return {
        'means': {g: {c: statistics.fmean(r[c] for r in rs) for c in columns} for g, rs in groups.items()},
        'compute_matched': {g: [paired(rs, f'{name}_r{b}', BASELINE_COLUMN[b])
                                for b in BASELINE_COLUMN for name in policy_names]
                            for g, rs in groups.items()},
    }


def external(policies: dict, protocol: dict = PROTOCOL) -> dict:
    with open(EXTERNAL_RAW, encoding='utf-8', newline='') as handle:
        reference = {(r['case_id'], r['mode']): r for r in csv.DictReader(handle)}
    instances, optimum = [], []
    for case in build_main_cases():
        f = case['factors']
        if case['group'] != 'primary' or f['num_tasks'] != 8:
            continue
        for mode in ('fixed', 'joint'):
            ref = reference[(case['case_id'], mode)]
            if ref['solver_status'] != 'OPTIMAL':
                raise ValueError('External n=8 reference must be OPTIMAL')
            instances.append(Instance(_data(case), mode, 8, f['num_machines'], f['alpha_percent'],
                                      f['beta_percent'], f['tau_percent'], f['instance_seed']))
            optimum.append(int(ref['total_tardiness']))
    rows, _ = evaluate(instances, policies, protocol)
    columns = [c for c in rows[0] if c not in ('seed', 'num_tasks', 'num_machines', 'alpha_percent',
                                               'beta_percent', 'tau_percent', 'mode')]
    return {'instances': len(rows),
            'mean_gap_to_optimum': {c: statistics.fmean(r[c] - o for r, o in zip(rows, optimum)) for c in columns},
            'optimal_hits': {c: sum(r[c] == o for r, o in zip(rows, optimum)) for c in columns}}


def run_experiment(output_dir: Path, protocol: dict = PROTOCOL) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    spec = protocol['test']
    test_set = make_instances(range(*spec['seeds']), sampler_seed=spec['sampler_seed'], balanced=spec['balanced'])
    policies = load_policies()
    rows, seconds = evaluate(test_set, policies, protocol)
    manifest = {
        'experiment': 'exp_037_sampling_decoding',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'protocol': protocol,
        'test_instances': len(rows),
        'mean_seconds_per_instance': seconds,
        'test_summary': summarize(rows, list(policies)),
        'external_g3_n8': external(policies, protocol),
        'all_plans_g1_checked': True,
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'research_status': 'not_achieved',
        'environment': {
            'python': platform.python_version(), 'platform': platform.platform(),
            'numpy': importlib.metadata.version('numpy'), 'scipy': importlib.metadata.version('scipy'),
            'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                         text=True, check=False).stdout.strip(),
        },
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    }
    with open(output_dir / 'test_rows.csv', 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n',
                                              encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'experiments' / 'runs' / 'exp_037_sampling_decoding')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    manifest = run_experiment(args.output_dir)
    LOGGER.info('test means: %s', json.dumps(manifest['test_summary']['means']['all']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
