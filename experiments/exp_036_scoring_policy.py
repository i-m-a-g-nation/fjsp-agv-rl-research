"""Train the per-action scoring policy and compare it with EDD/MDD/ATC once on test.

Protocol fixed before the run: G3A-generator instances with disjoint seed
ranges (train 2000, validation 200, test 600 balanced over 6 sizes), three
training seeds, behaviour cloning then self-critical REINFORCE, checkpoint
chosen on validation only. Every plan is G1-checked. An external check on
the G3A primary cases compares with exp_035 CP-SAT (OPTIMAL for n=8).
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

from src.graduation.dispatch_rules import DISPATCH_RULES, solve_dispatch_rule
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data
from src.graduation.scoring_policy import run_episode
from src.graduation.scoring_training import Instance, make_instances, train

LOGGER = logging.getLogger(__name__)
PROTOCOL = {
    'train': {'seeds': [10000, 12000], 'sampler_seed': 1, 'balanced': False},
    'validation': {'seeds': [20000, 20200], 'sampler_seed': 2, 'balanced': False},
    'test': {'seeds': [30000, 30600], 'sampler_seed': 3, 'balanced': True},
    'training_seeds': [0, 1, 2],
    'hyperparameters': {'hidden_size': 32, 'bc_epochs': 15, 'bc_learning_rate': 3e-3,
                        'rl_epochs': 12, 'rl_learning_rate': 1e-3, 'rl_batch_size': 16,
                        'rl_samples_per_instance': 4},
    'selection': 'lowest validation mean greedy total tardiness over init/bc/rl epochs',
    'external_reference': 'experiments/results/exp_035_graduation_main_v2_v1/rows.csv',
}
EXTERNAL_RAW = ROOT / PROTOCOL['external_reference']
SOURCES = ('src/graduation/dispatch_rules.py', 'src/graduation/action_features.py',
           'src/graduation/scoring_policy.py', 'src/graduation/scoring_training.py',
           'src/graduation/rl_environment.py', 'src/graduation/feasibility.py',
           'experiments/exp_036_scoring_policy.py')


def _split(name: str, protocol: dict = PROTOCOL) -> list[Instance]:
    spec = protocol[name]
    return make_instances(range(*spec['seeds']), sampler_seed=spec['sampler_seed'], balanced=spec['balanced'])


def _checked(result, instance_data, mode) -> int:
    accepted, issues = check_parallel_maintenance_feasibility(result, instance_data, mode=mode)
    if not accepted:
        raise ValueError(f'G1 rejected a plan: {issues}')
    return result.total_tardiness


def evaluate(instances: list[Instance], policies: dict) -> list[dict]:
    rows = []
    for instance in instances:
        row = {'seed': instance.seed, 'num_tasks': instance.num_tasks, 'num_machines': instance.num_machines,
               'alpha_percent': instance.alpha_percent, 'beta_percent': instance.beta_percent,
               'tau_percent': instance.tau_percent, 'mode': instance.mode}
        for rule in DISPATCH_RULES:
            row[rule] = _checked(solve_dispatch_rule(instance.data, mode=instance.mode, rule=rule),
                                 instance.data, instance.mode)
        row['best_rule'] = min(row[rule] for rule in DISPATCH_RULES)
        for name, policy in policies.items():
            row[name] = _checked(run_episode(policy, instance.data, mode=instance.mode).result,
                                 instance.data, instance.mode)
        rows.append(row)
    return rows


def paired(rows: list[dict], method: str, baseline: str) -> dict:
    diffs = [row[method] - row[baseline] for row in rows]
    nonzero = [d for d in diffs if d != 0]
    p_value = float(wilcoxon(nonzero).pvalue) if len(nonzero) >= 10 else None
    base_mean = statistics.fmean(row[baseline] for row in rows)
    return {'method': method, 'baseline': baseline, 'n': len(rows),
            'method_mean': statistics.fmean(row[method] for row in rows), 'baseline_mean': base_mean,
            'mean_difference': statistics.fmean(diffs),
            'relative_difference': statistics.fmean(diffs) / base_mean if base_mean else None,
            'wins': sum(d < 0 for d in diffs), 'ties': sum(d == 0 for d in diffs),
            'losses': sum(d > 0 for d in diffs), 'wilcoxon_p_nonzero': p_value}


def summarize(rows: list[dict], policy_names: list[str]) -> dict:
    methods = [*DISPATCH_RULES, 'best_rule', *policy_names]
    groups = {'all': rows}
    for n, m in sorted({(r['num_tasks'], r['num_machines']) for r in rows}):
        groups[f'n{n}-m{m}'] = [r for r in rows if (r['num_tasks'], r['num_machines']) == (n, m)]
    means = {g: {method: statistics.fmean(r[method] for r in rs) for method in methods} for g, rs in groups.items()}
    comparisons = {g: [paired(rs, name, base) for name in policy_names for base in ('MDD', 'ATC', 'best_rule')]
                   for g, rs in groups.items()}
    seed_means = [means['all'][name] for name in policy_names]
    return {'means': means, 'paired': comparisons,
            'policy_seed_mean': statistics.fmean(seed_means),
            'policy_seed_std': statistics.stdev(seed_means) if len(seed_means) > 1 else 0.0}


def external_rows(policies: dict) -> list[dict]:
    with open(EXTERNAL_RAW, encoding='utf-8', newline='') as handle:
        reference = {(r['case_id'], r['mode']): r for r in csv.DictReader(handle)}
    instances, refs = [], []
    for case in build_main_cases():
        if case['group'] != 'primary':
            continue
        f = case['factors']
        for mode in ('fixed', 'joint'):
            instances.append(Instance(_data(case), mode, f['num_tasks'], f['num_machines'], f['alpha_percent'],
                                      f['beta_percent'], f['tau_percent'], f['instance_seed']))
            refs.append(reference[(case['case_id'], mode)])
    rows = evaluate(instances, policies)
    for row, ref in zip(rows, refs):
        row.update(case_id=ref['case_id'], cp_sat=int(ref['total_tardiness']), cp_sat_status=ref['solver_status'])
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run_experiment(output_dir: Path, protocol: dict = PROTOCOL) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / 'checkpoints').mkdir()
    started = time.monotonic()
    train_set, val_set, test_set = (_split(name, protocol) for name in ('train', 'validation', 'test'))
    policies, histories, checkpoints = {}, {}, {}
    for seed in protocol['training_seeds']:
        name = f'policy_s{seed}'
        hp = protocol['hyperparameters']
        policy, history = train(train_set, val_set, seed=seed, hidden_size=hp['hidden_size'],
                                bc_epochs=hp['bc_epochs'], bc_learning_rate=hp['bc_learning_rate'],
                                rl_epochs=hp['rl_epochs'], rl_learning_rate=hp['rl_learning_rate'],
                                log=lambda entry, s=seed: LOGGER.info('seed %d %s', s, json.dumps(entry)))
        policies[name], histories[name] = policy, history
        checkpoints[name] = policy.save(output_dir / 'checkpoints' / f'{name}.npz')
    validation = evaluate(val_set, policies)
    test = evaluate(test_set, policies)
    external = external_rows(policies)
    names = list(policies)
    n8_optimal = [r for r in external if r['num_tasks'] == 8 and r['cp_sat_status'] == 'OPTIMAL']
    manifest = {
        'experiment': 'exp_036_scoring_policy',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'protocol': protocol,
        'split_sizes': {'train': len(train_set), 'validation': len(val_set), 'test': len(test_set)},
        'selected_checkpoints': {name: h[-1] for name, h in histories.items()},
        'checkpoint_sha256': checkpoints,
        'validation_summary': summarize(validation, names),
        'test_summary': summarize(test, names),
        'external_g3_primary': {
            'summary': summarize(external, names),
            'n8_optimal_rows': len(n8_optimal),
            'n8_mean_gap_to_optimum': {method: statistics.fmean(r[method] - r['cp_sat'] for r in n8_optimal)
                                       for method in [*DISPATCH_RULES, 'best_rule', *names]},
            'n8_optimal_hits': {method: sum(r[method] == r['cp_sat'] for r in n8_optimal)
                                for method in [*DISPATCH_RULES, 'best_rule', *names]},
        },
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
    _write_csv(output_dir / 'validation_rows.csv', validation)
    _write_csv(output_dir / 'test_rows.csv', test)
    _write_csv(output_dir / 'external_g3_rows.csv', external)
    (output_dir / 'training_log.json').write_text(json.dumps(histories, indent=1) + '\n', encoding='utf-8')
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n',
                                              encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'experiments' / 'runs' / 'exp_036_scoring_policy')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    manifest = run_experiment(args.output_dir)
    LOGGER.info('test means: %s', json.dumps(manifest['test_summary']['means']['all']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
