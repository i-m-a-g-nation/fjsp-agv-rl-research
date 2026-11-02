"""Innovation project L2 pilot: does the imitation + REINFORCE pipeline train at all?

Pilot only (docs/plans/innovation_rl_design.md, section 5): small budget,
training and validation instances from ``logistics.generator`` with the
Homayouni & Fontes layouts (local, hashed); no test instance is touched.
Output goes to ``experiments/runs/`` by default and is not archived; no
conclusion about the method is drawn from it.

Reports the validation history (greedy makespan / best avoided rule) and,
for the selected checkpoint, the per-configuration validation comparison
with the best avoided rule and with EFT. Writes history.csv, validation.csv,
policy.npz and manifest.json.
"""

from __future__ import annotations

from pathlib import Path
import statistics
import time

from _common import ROOT, parse_args, provenance, sha256, write_csv, write_json

from fjsp_lab.logistics import check_logistics_feasibility, parse_layout
from fjsp_lab.logistics.generator import split
from fjsp_lab.logistics.policy import best_rule, run_episode, train
from fjsp_lab.logistics.rules import solve_rule

BUDGET = {'train_instances': 400, 'validation_instances': 50, 'bc_epochs': 15, 'rl_epochs': 20,
          'samples_per_instance': 4, 'rl_batch_size': 8, 'hidden_size': 32, 'seed': 0}


def main() -> None:
    args = parse_args(__doc__.splitlines()[0], 'l2_policy_pilot',
                      lambda p: p.add_argument('--layout-dir', type=Path, default=ROOT / 'instances/external/HomayouniFontes'))
    files = {k: args.layout_dir / f'layout_{k}M.txt' for k in (4, 5, 6, 8)}
    layouts = {k: parse_layout(path.read_text(encoding='utf-8'), k) for k, path in files.items()}
    train_set = split('train', BUDGET['train_instances'], layouts)
    val_set = split('validation', BUDGET['validation_instances'], layouts)
    started = time.perf_counter()
    policy, history = train([g.data for g in train_set], [g.data for g in val_set], seed=BUDGET['seed'],
                            hidden_size=BUDGET['hidden_size'], bc_epochs=BUDGET['bc_epochs'],
                            rl_epochs=BUDGET['rl_epochs'], samples_per_instance=BUDGET['samples_per_instance'],
                            rl_batch_size=BUDGET['rl_batch_size'], log=lambda h: print(h, flush=True))
    training_seconds = round(time.perf_counter() - started, 1)
    rows = []
    for g in val_set:
        episode = run_episode(policy, g.data)
        accepted, issues = check_logistics_feasibility(episode.schedule, g.data)
        if not accepted:
            raise ValueError(f'Checker rejected a policy schedule: {issues}')
        rule, reference = best_rule(g.data)
        rows.append({'seed': g.seed, 'config': g.config, 'jobs': g.data.num_jobs, 'machines': g.data.num_machines,
                     'policy': episode.makespan, 'best_rule': reference, 'best_rule_name': rule,
                     'eft': solve_rule(g.data, 'EFT', avoid_deadlock=True).makespan})
    summary = []
    for config in sorted({r['config'] for r in rows}) + ['all']:
        group = [r for r in rows if config in ('all', r['config'])]
        summary.append({'config': config, 'n': len(group),
                        'mean_ratio_to_best_rule': round(statistics.fmean(r['policy'] / r['best_rule'] for r in group), 4),
                        'mean_ratio_to_eft': round(statistics.fmean(r['policy'] / r['eft'] for r in group), 4),
                        'better_than_best_rule': sum(r['policy'] < r['best_rule'] for r in group),
                        'equal': sum(r['policy'] == r['best_rule'] for r in group)})
    write_csv(args.output_dir / 'history.csv', history)
    write_csv(args.output_dir / 'validation.csv', rows)
    write_csv(args.output_dir / 'validation_summary.csv', summary)
    digest = policy.save(args.output_dir / 'policy.npz')
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'l2_policy_pilot', 'budget': BUDGET, 'training_seconds': training_seconds,
        'policy_sha256': digest, 'layouts_sha256': {p.name: sha256(p) for p in files.values()},
        'provenance': provenance(__file__)})
    for item in summary:
        print(item)


if __name__ == '__main__':
    main()
