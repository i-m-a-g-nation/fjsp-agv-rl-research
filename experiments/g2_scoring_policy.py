"""Graduation: train the NumPy scoring policy (3 seeds) and compare it with rules on the test split.

Protocol: instances from fjsp_lab.maintenance.generator.SPLITS (train 2000,
validation 200, test 600 balanced over six sizes, disjoint seeds). Per
training seed: behaviour cloning on the best of EDD/MDD/ATC, then
self-critical REINFORCE; the checkpoint with the lowest validation mean
greedy tardiness is kept. The test split is used once, after training,
with compute-matched budgets: 1 rollout vs MDD, 3 vs best of EDD/MDD/ATC,
9 vs best of the 9-rule portfolio. Writes checkpoints/, test_rows.csv,
training_log.json and manifest.json.
"""

from __future__ import annotations

import json
import logging
import statistics
import time

from _common import by_size, checked_tardiness, paired, parse_args, provenance, write_csv, write_json

from fjsp_lab.maintenance.generator import SPLITS, split_instances
from fjsp_lab.maintenance.rules import RULE_PORTFOLIO, solve_dispatch_rule
from fjsp_lab.maintenance.scoring_policy import best_of_rollouts, train

LOGGER = logging.getLogger(__name__)
TRAINING_SEEDS = (0, 1, 2)
HYPERPARAMETERS = {'hidden_size': 32, 'bc_epochs': 15, 'bc_learning_rate': 3e-3, 'rl_epochs': 12,
                   'rl_learning_rate': 1e-3}
ROLLOUTS = {'r1': 0, 'r3': 2, 'r9': 8}            # extra sampled rollouts after the greedy one
BASELINE = {'r1': 'MDD', 'r3': 'best_of_3_rules', 'r9': 'best_of_9_rules'}
FACTORS = ('seed', 'num_tasks', 'num_machines', 'alpha_percent', 'beta_percent', 'tau_percent', 'mode')


def rule_columns(instance) -> dict:
    values = {}
    for rule, k in RULE_PORTFOLIO:
        label = rule if rule != 'ATC' else f'ATC_k{k:g}'
        plan = solve_dispatch_rule(instance.data, mode=instance.mode, rule=rule, atc_k=k)
        values[label] = checked_tardiness(plan, instance.data, instance.mode)
    out = {'EDD': values['EDD'], 'MDD': values['MDD'], 'ATC': values['ATC_k1']}
    out['best_of_3_rules'] = min(out.values())
    out['best_of_9_rules'] = min(values.values())
    return out


def evaluate(instances, policies: dict) -> list[dict]:
    rows = []
    for instance in instances:
        row = {f: getattr(instance, f) for f in FACTORS} | rule_columns(instance)
        for name, policy in policies.items():
            for label, samples in ROLLOUTS.items():
                plan = best_of_rollouts(policy, instance.data, mode=instance.mode, samples=samples, seed=0)
                row[f'{name}_{label}'] = checked_tardiness(plan, instance.data, instance.mode)
        rows.append(row)
    return rows


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g2_scoring_policy')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    started = time.monotonic()
    train_set, val_set, test_set = (split_instances(name) for name in ('train', 'validation', 'test'))
    (args.output_dir / 'checkpoints').mkdir()
    policies, histories, digests = {}, {}, {}
    for seed in TRAINING_SEEDS:
        name = f'policy_s{seed}'
        policy, history = train(train_set, val_set, seed=seed, **HYPERPARAMETERS,
                                log=lambda entry, s=seed: LOGGER.info('seed %d %s', s, json.dumps(entry)))
        policies[name], histories[name] = policy, history
        digests[name] = policy.save(args.output_dir / 'checkpoints' / f'{name}.npz')
    final = min(policies, key=lambda name: histories[name][-1]['val_mean_tardiness'])
    rows = evaluate(test_set, policies)
    summary = {}
    for group, selected in by_size(rows).items():
        summary[group] = {'mean': {c: statistics.fmean(r[c] for r in selected) for c in rows[0] if c not in FACTORS},
                          'paired': [paired(selected, f'{name}_{label}', BASELINE[label])
                                     for name in policies for label in ROLLOUTS]}
    write_csv(args.output_dir / 'test_rows.csv', rows)
    write_json(args.output_dir / 'training_log.json', histories)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g2_scoring_policy', 'splits': {k: [v[0].start, v[0].stop, v[1], v[2]] for k, v in SPLITS.items()},
        'training_seeds': TRAINING_SEEDS, 'hyperparameters': HYPERPARAMETERS, 'rollouts': ROLLOUTS,
        'checkpoint_sha256': digests, 'final_model': final,
        'selected': {name: h[-1] for name, h in histories.items()}, 'test_summary': summary,
        'elapsed_seconds': round(time.monotonic() - started, 1), **provenance(__file__)})
    LOGGER.info('test means: %s', json.dumps(summary['all']['mean']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
