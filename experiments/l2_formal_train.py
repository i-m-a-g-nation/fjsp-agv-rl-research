"""Innovation project L2 formal training (docs/protocols/l2_formal_protocol.md, approved 2026-11-03).

Three training seeds (0, 1, 2), trained one after another; within a seed the
episodes run in 18 worker processes (results do not depend on the number of
workers). 400 training and 100 validation instances from
``logistics.generator`` with the Homayouni & Fontes layouts (local, hashed);
imitation 15 epochs (lr 3e-3), REINFORCE 120 epochs (K = 8, batches of 8,
lr 1e-3); checkpoint chosen on validation only. No test instance is used.

Writes, per seed, policy_seed<s>.npz, history_seed<s>.csv and
validation_seed<s>.csv (greedy makespan against the best avoided rule), plus
summary.csv and manifest.json with the checkpoint hashes.
"""

from __future__ import annotations

from pathlib import Path
import statistics
import time

from _common import ROOT, parse_args, provenance, sha256, write_csv, write_json

from fjsp_lab.logistics import check_logistics_feasibility, parse_layout
from fjsp_lab.logistics.generator import split
from fjsp_lab.logistics.policy import best_rule, run_episode, train

BUDGET = {'train_instances': 400, 'validation_instances': 100, 'bc_epochs': 15, 'bc_learning_rate': 3e-3,
          'rl_epochs': 120, 'rl_learning_rate': 1e-3, 'samples_per_instance': 8, 'rl_batch_size': 8,
          'hidden_size': 32}
SEEDS = (0, 1, 2)
WORKERS = 18


def main() -> None:
    args = parse_args(__doc__.splitlines()[0], 'l2_formal_train',
                      lambda p: p.add_argument('--layout-dir', type=Path, default=ROOT / 'instances/external/HomayouniFontes'))
    files = {k: args.layout_dir / f'layout_{k}M.txt' for k in (4, 5, 6, 8)}
    layouts = {k: parse_layout(path.read_text(encoding='utf-8'), k) for k, path in files.items()}
    train_set = [g.data for g in split('train', BUDGET['train_instances'], layouts)]
    val_generated = split('validation', BUDGET['validation_instances'], layouts)
    val_set = [g.data for g in val_generated]
    manifest = {'experiment': 'l2_formal_train', 'budget': BUDGET, 'seeds': list(SEEDS), 'workers': WORKERS,
                'layouts_sha256': {p.name: sha256(p) for p in files.values()}, 'checkpoints': {},
                'provenance': provenance(__file__)}
    summary = []
    for seed in SEEDS:
        started = time.perf_counter()
        policy, history = train(train_set, val_set, seed=seed, hidden_size=BUDGET['hidden_size'],
                                bc_epochs=BUDGET['bc_epochs'], bc_learning_rate=BUDGET['bc_learning_rate'],
                                rl_epochs=BUDGET['rl_epochs'], rl_learning_rate=BUDGET['rl_learning_rate'],
                                samples_per_instance=BUDGET['samples_per_instance'],
                                rl_batch_size=BUDGET['rl_batch_size'], workers=WORKERS,
                                log=lambda h, s=seed: print(f'seed {s}', h, flush=True))
        seconds = round(time.perf_counter() - started, 1)
        digest = policy.save(args.output_dir / f'policy_seed{seed}.npz')
        manifest['checkpoints'][f'policy_seed{seed}.npz'] = {'sha256': digest, 'training_seconds': seconds,
                                                             'selected': history[-1]}
        rows = []
        for g in val_generated:
            episode = run_episode(policy, g.data)
            accepted, issues = check_logistics_feasibility(episode.schedule, g.data)
            if not accepted:
                raise ValueError(f'Checker rejected a policy schedule: {issues}')
            rows.append({'seed': g.seed, 'config': g.config, 'policy': episode.makespan,
                         'best_rule': best_rule(g.data)[1]})
        write_csv(args.output_dir / f'history_seed{seed}.csv', history)
        write_csv(args.output_dir / f'validation_seed{seed}.csv', rows)
        summary.append({'training_seed': seed, 'selected_phase': history[-1]['from'],
                        'selected_epoch': history[-1]['epoch'],
                        'val_ratio_to_best_rule': round(statistics.fmean(r['policy'] / r['best_rule'] for r in rows), 4),
                        'val_better_than_best_rule': sum(r['policy'] < r['best_rule'] for r in rows),
                        'training_seconds': seconds})
        write_json(args.output_dir / 'manifest.json', manifest)       # after every seed, in case of interruption
    write_csv(args.output_dir / 'summary.csv', summary)
    for item in summary:
        print(item)


if __name__ == '__main__':
    main()
