"""Innovation project L2 formal test (docs/protocols/l2_formal_protocol.md, approved 2026-11-03).

Uses the three checkpoints of ``experiments/results/l2_formal_train`` (hashes
checked against its manifest) once on the test sets:

* T1: the 10 Deroussi & Norre instances (benchmark layout);
* T2: Brandimarte mk01-05, mk07 with the Homayouni & Fontes layouts;

each in 5 configurations (benchmark conventions; blocking with input
buffers inf / 2 / 1 / 0), 2 vehicles, no return to L/U.

Per case: the four avoided rules (and their per-case best); per training
seed the greedy policy and greedy + 8 / + 32 samples (sampling seed fixed per
case and training seed); SA with as many evaluations as the 32-sample policy
builds schedules (33, seed 0); SA with the wall time of the 32-sample policy
on that case and seed. Everything runs in one process, one after another,
so times are comparable. Archived references: CP-SAT of ``l1_benchmark``
(T1) and SA of ``l1_search``. Hypotheses H1-H4 (one-sided paired Wilcoxon,
Holm over H1-H4 within each training seed; a hypothesis holds if it holds
for at least 2 of the 3 seeds) are evaluated as fixed in the protocol.
Writes rows.csv, summary.csv, hypotheses.csv and manifest.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import statistics
import time
import zlib

import numpy as np

from _common import ROOT, parse_args, provenance, read_csv, sha256, write_csv, write_json

from fjsp_lab.fjsp import load_project_benchmark_file
from fjsp_lab.logistics import LogisticsInstance, check_logistics_feasibility, load_fjspt, parse_layout
from fjsp_lab.logistics.metaheuristics import solve_sa
from fjsp_lab.logistics.policy import LogisticsPolicy, run_episode
from fjsp_lab.logistics.rules import RULES, solve_rule

CONFIGS = {'bench': (False, None), 'block-inf': (True, None), 'block-2': (True, 2),
           'block-1': (True, 1), 'block-0': (True, 0)}               # name: (blocking, buffer capacity)
T1 = tuple(f'fjsp{i}' for i in range(1, 11))
T2 = ('mk01', 'mk02', 'mk03', 'mk04', 'mk05', 'mk07')
SEEDS = (0, 1, 2)
SAMPLES = (8, 32)


def checked(schedule, data) -> int:
    accepted, issues = check_logistics_feasibility(schedule, data)
    if not accepted:
        raise ValueError(f'Checker rejected a returned schedule: {issues}')
    return schedule.makespan


def cases(small_dir: Path, large_dir: Path):
    for name in T1:
        for config, (blocking, buffer) in CONFIGS.items():
            yield 'T1', name, config, load_fjspt(small_dir / 'DeroussiNorre' / f'{name}.txt',
                                                 small_dir / 'DeroussiNorre_layout.txt',
                                                 blocking=blocking, buffer_capacity=buffer)
    for name in T2:
        production = load_project_benchmark_file(ROOT / f'instances/fjsplib/Brandimarte1993/{name}.fjs')
        layout = large_dir / f'layout_{production.num_machines}M.txt'
        travel = parse_layout(layout.read_text(encoding='utf-8'), production.num_machines)
        for config, (blocking, buffer) in CONFIGS.items():
            yield 'T2', name, config, LogisticsInstance.create(production, travel, num_vehicles=2,
                                                               buffer_capacity=buffer, blocking=blocking,
                                                               return_to_lu=False)


def main() -> None:
    args = parse_args(__doc__.splitlines()[0], 'l2_formal_test', lambda p: (
        p.add_argument('--train-dir', type=Path, default=ROOT / 'experiments/results/l2_formal_train'),
        p.add_argument('--small-dir', type=Path, default=ROOT / 'instances/external/FJSPT'),
        p.add_argument('--large-dir', type=Path, default=ROOT / 'instances/external/HomayouniFontes')))
    train_manifest = json.loads((args.train_dir / 'manifest.json').read_text(encoding='utf-8'))
    policies = {}
    for seed in SEEDS:
        name = f'policy_seed{seed}.npz'
        policies[seed] = LogisticsPolicy.load(args.train_dir / name,
                                              expected_sha256=train_manifest['checkpoints'][name]['sha256'])
    references = reference_values()
    rows = []
    for test_set, name, config, data in cases(args.small_dir, args.large_dir):
        row = {'test_set': test_set, 'instance': name, 'config': config, **references.get((name, config), {})}
        for rule in RULES[:4]:
            row[rule] = checked(solve_rule(data, rule, avoid_deadlock=True), data)
        row['best_rule'] = min(row[rule] for rule in RULES[:4])
        for seed, policy in policies.items():
            started = time.perf_counter()
            greedy = checked(run_episode(policy, data).schedule, data)
            row[f'greedy_s{seed}'] = greedy
            row[f'greedy_time_s{seed}'] = round(time.perf_counter() - started, 4)
            rng = np.random.default_rng(zlib.crc32(f'{name}/{config}/{seed}'.encode()))
            best = greedy
            for count in range(1, max(SAMPLES) + 1):
                best = min(best, checked(run_episode(policy, data, rng=rng).schedule, data))
                if count in SAMPLES:
                    row[f'sample{count}_s{seed}'] = best
                    row[f'sample{count}_time_s{seed}'] = round(time.perf_counter() - started, 4)
            limit = row[f'sample{max(SAMPLES)}_time_s{seed}']
            row[f'sa_equal_time_s{seed}'] = checked(solve_sa(data, evaluations=10 ** 9, seed=0,
                                                             time_limit=limit).schedule, data)
        row['sa_equal_evaluations'] = checked(solve_sa(data, evaluations=max(SAMPLES) + 1, seed=0).schedule, data)
        rows.append(row)
        print(test_set, name, config, 'done', flush=True)
    inputs = sorted(args.large_dir.glob('layout_*M.txt')) + [args.small_dir / 'DeroussiNorre_layout.txt'] + \
        [args.small_dir / 'DeroussiNorre' / f'{n}.txt' for n in T1]
    write_csv(args.output_dir / 'rows.csv', rows)
    write_csv(args.output_dir / 'summary.csv', summarize(rows))
    write_csv(args.output_dir / 'hypotheses.csv', hypotheses(rows))
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'l2_formal_test', 'train_manifest_sha256': sha256(args.train_dir / 'manifest.json'),
        'checkpoints': {f'policy_seed{s}.npz': train_manifest['checkpoints'][f'policy_seed{s}.npz']['sha256'] for s in SEEDS},
        'inputs_sha256': {p.name if p.parent.name != 'DeroussiNorre' else f'DeroussiNorre/{p.name}': sha256(p)
                          for p in inputs},
        'references_sha256': {'l1_benchmark/rows.csv': sha256(ROOT / 'experiments/results/l1_benchmark/rows.csv'),
                              'l1_search/rows.csv': sha256(ROOT / 'experiments/results/l1_search/rows.csv')},
        'provenance': provenance(__file__)})


def reference_values() -> dict:
    """CP-SAT (T1) from l1_benchmark and the best SA seed of l1_search, per (instance, config)."""
    refs: dict = {}
    for r in read_csv(ROOT / 'experiments/results/l1_benchmark/rows.csv'):
        if r['method'] == 'CP-SAT' and r['makespan']:
            refs.setdefault((r['instance'], r['config']), {}).update(
                cpsat=int(r['makespan']), cpsat_status=r['status'])
    for r in read_csv(ROOT / 'experiments/results/l1_search/rows.csv'):
        if r['method'] == 'SA':
            entry = refs.setdefault((r['instance'], r['config']), {})
            entry['sa_reference'] = min(entry.get('sa_reference', int(r['makespan'])), int(r['makespan']))
    return refs


def _ratio(rows: list[dict], method: str, reference: str) -> float:
    return round(statistics.fmean(float(r[method]) / float(r[reference]) for r in rows), 4)


def summarize(rows: list[dict]) -> list[dict]:
    """Mean ratios per test set and configuration (and overall), per training seed."""
    summary = []
    for test_set in ('T1', 'T2'):
        for config in list(CONFIGS) + ['all']:
            group = [r for r in rows if r['test_set'] == test_set and config in ('all', r['config'])]
            for seed in SEEDS:
                item = {'test_set': test_set, 'config': config, 'training_seed': seed, 'n': len(group)}
                for method in (f'greedy_s{seed}', f'sample8_s{seed}', f'sample32_s{seed}', f'sa_equal_time_s{seed}',
                               'sa_equal_evaluations', 'EFT'):
                    label = method.replace(f'_s{seed}', '')
                    item[f'{label}/best_rule'] = _ratio(group, method, 'best_rule')
                    item[f'{label}/sa_reference'] = _ratio(group, method, 'sa_reference')
                optimal = [r for r in group if r.get('cpsat_status') == 'OPTIMAL']
                if optimal:
                    item['n_optimal'] = len(optimal)
                    for method in (f'greedy_s{seed}', f'sample32_s{seed}'):
                        item[f'{method.replace(f"_s{seed}", "")}/optimum'] = _ratio(optimal, method, 'cpsat')
                item['mean_sample32_seconds'] = round(statistics.fmean(float(r[f'sample32_time_s{seed}'])
                                                                       for r in group), 3)
                summary.append(item)
    return summary


def hypotheses(rows: list[dict]) -> list[dict]:
    """H1-H4 per training seed: one-sided Wilcoxon (policy smaller), Holm over the four within a seed."""
    from scipy.stats import wilcoxon

    tests = {'H1': ('greedy', 'EFT', ('T1', 'T2')), 'H2': ('sample32', 'best_rule', ('T1', 'T2')),
             'H3': ('sample32', 'sa_equal_time', ('T2',)), 'H4': ('sample32', 'sa_equal_time', ('T1',))}
    results = []
    for seed in SEEDS:
        found = []
        for name, (method, baseline, sets) in tests.items():
            group = [r for r in rows if r['test_set'] in sets]
            ours = [float(r[f'{method}_s{seed}']) for r in group]
            theirs = [float(r[baseline if baseline in ('EFT', 'best_rule') else f'{baseline}_s{seed}']) for r in group]
            diffs = [a - b for a, b in zip(ours, theirs)]
            p = float(wilcoxon(diffs, alternative='less').pvalue) if any(diffs) else 1.0
            found.append({'hypothesis': name, 'training_seed': seed, 'n': len(diffs),
                          'mean_policy': round(statistics.fmean(ours), 3), 'mean_baseline': round(statistics.fmean(theirs), 3),
                          'wins': sum(d < 0 for d in diffs), 'ties': sum(d == 0 for d in diffs),
                          'losses': sum(d > 0 for d in diffs), 'p_one_sided': p})
        ordered = sorted(found, key=lambda f: f['p_one_sided'])
        running = 0.0
        for rank, item in enumerate(ordered):                     # Holm step-down adjusted p-values
            running = max(running, min(1.0, (len(ordered) - rank) * item['p_one_sided']))
            item['p_holm'] = running
            item['holds'] = running < 0.05
        results += found
    for name in tests:
        held = sum(r['holds'] for r in results if r['hypothesis'] == name)
        results.append({'hypothesis': name, 'training_seed': 'all', 'seeds_holding': held, 'holds': held >= 2})
    return results


if __name__ == '__main__':
    main()
