"""Graduation G4: quality-time curves, the pre-registered tests H1-H3 and a figure.

Inputs: ``--search`` (one or more g7_g4_search_curves runs; a later run replaces
the methods it contains, e.g. a re-timing of IGA and SA) and ``--policy``
(g8_g4_policy_curves run).
Value of a method at time budget t (seconds per instance):
* rules: their value (all finish within milliseconds);
* IGA, GA: best value found within t (from the improvement trace);
* SA: the run whose time limit is t;
* CP-SAT: best incumbent objective within t (an upper bound on that plan's tardiness);
* RL: best of the policy points finished within t (greedy, then greedy + K samples),
  GPU timing (``RL``) and single-thread CPU timing (``RL-cpu``, greedy and K=4 only).
A method with nothing finished by t has no value at t; coverage is reported.
best_known = minimum over every method and run; gap = (T - best_known) / max(1, best_known).
Writes summary.json, curves.csv and curves.png.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import statistics

from _common import parse_args, provenance, sha256, write_csv, write_json

LOGGER = logging.getLogger(__name__)
BUDGETS = (0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)
METHODS = ('MDD', 'ATC', 'EDD', 'GA', 'SA', 'IGA', 'CP-SAT', 'RL', 'RL-cpu')
H1_BUDGETS, H2_BUDGETS = (0.05, 0.1, 0.2), (2.0, 5.0, 10.0)


def read_jsonl(path: Path) -> dict:
    with open(path, encoding='utf-8') as handle:
        return {(row['case_id'], row['mode']): row for row in map(json.loads, handle)}


def policy_points(timing: dict) -> list[tuple[float, int]]:
    greedy = timing['greedy']
    points = [(greedy['seconds'], greedy['value'])]
    for key, point in timing.items():
        if key.startswith('sample'):
            points.append((greedy['seconds'] + point['seconds'], min(greedy['value'], point['value'])))
    return points


def value_at(search: dict, policy: dict, method: str, t: float):
    if method in ('MDD', 'ATC', 'EDD'):
        return search[method]['value'] if search[method]['seconds'] <= t else None
    if method in ('IGA', 'GA'):
        found = [v for seconds, _, v in search[method]['trace'] if seconds <= t]
        return min(found) if found else None
    if method == 'SA':
        return search['SA'][str(t)]['value']
    if method == 'CP-SAT':
        found = [objective for seconds, objective, _ in search['CP-SAT']['trace'] if seconds <= t]
        return int(min(found)) if found else None
    points = policy_points(policy['device' if method == 'RL' else 'cpu'])
    found = [v for seconds, v in points if seconds <= t]
    return min(found) if found else None


def best_known(search: dict, policy: dict) -> int:
    values = [search[r]['value'] for r in ('MDD', 'ATC', 'EDD')]
    values += [search[a]['value'] for a in ('IGA', 'GA')] + [run['value'] for run in search['SA'].values()]
    if search['CP-SAT']['value'] is not None:
        values.append(search['CP-SAT']['value'])
    values += [v for side in ('device', 'cpu') for _, v in policy_points(policy[side])]
    return min(values)


def wilcoxon_test(rows: list[dict], method: str, other: str, t: float) -> dict:
    from scipy.stats import wilcoxon

    if not rows:
        return {'method': method, 'other': other, 'budget': t, 'instances': 0}
    both = [r for r in rows if r['values'][t][method] is not None and r['values'][t][other] is not None]
    diffs = [r['gap'][t][method] - r['gap'][t][other] for r in both]
    nonzero = [d for d in diffs if d != 0]
    return {'method': method, 'other': other, 'budget': t, 'instances': len(rows), 'compared': len(both),
            'method_coverage': sum(r['values'][t][method] is not None for r in rows) / len(rows),
            'mean_gap_method': statistics.fmean(r['gap'][t][method] for r in both) if both else None,
            'mean_gap_other': statistics.fmean(r['gap'][t][other] for r in both) if both else None,
            'wins': sum(d < 0 for d in diffs), 'ties': sum(d == 0 for d in diffs), 'losses': sum(d > 0 for d in diffs),
            'wilcoxon_p': float(wilcoxon(nonzero).pvalue) if len(nonzero) >= 10 else None}


def main() -> int:
    def extra(parser):
        parser.add_argument('--search', type=Path, nargs='+', required=True)
        parser.add_argument('--policy', type=Path, required=True)

    args = parse_args(__doc__.splitlines()[0], 'g9_g4_summary', extra)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)
    search, policy = read_jsonl(args.search[0] / 'rows.jsonl'), read_jsonl(args.policy / 'rows.jsonl')
    for override in args.search[1:]:
        for key, row in read_jsonl(override / 'rows.jsonl').items():
            search[key].update({m: row[m] for m in ('EDD', 'MDD', 'ATC', 'IGA', 'GA', 'SA', 'CP-SAT') if m in row})
    if set(search) != set(policy):
        raise ValueError('Search and policy runs cover different instances')
    rows = []
    for key in sorted(search):
        s, p = search[key], policy[key]
        bk = best_known(s, p)
        cp = s['CP-SAT']
        if cp['value'] is not None and cp['status'] == 'OPTIMAL' and bk < cp['value']:
            raise ValueError(f'{key}: a method beats a proven CP-SAT optimum')
        values = {t: {m: value_at(s, p, m, t) for m in METHODS} for t in BUDGETS}
        gap = {t: {m: None if v is None else (v - bk) / max(1, bk) for m, v in values[t].items()} for t in BUDGETS}
        rows.append({**{k: s[k] for k in ('case_id', 'mode', 'num_tasks', 'num_machines', 'profile',
                                            'alpha_percent', 'beta_percent', 'tau_percent')},
                     'best_known': bk, 'values': values, 'gap': gap})
    groups = {'all': rows, **{f'n{n}': [r for r in rows if r['num_tasks'] == n] for n in (20, 50, 100)},
              'n>=50': [r for r in rows if r['num_tasks'] >= 50]}
    groups = {name: selected for name, selected in groups.items() if selected}
    curves = []
    for name, selected in groups.items():
        for t in BUDGETS:
            for m in METHODS:
                found = [r['gap'][t][m] for r in selected if r['gap'][t][m] is not None]
                curves.append({'group': name, 'budget': t, 'method': m, 'coverage': len(found) / len(selected),
                               'mean_gap': statistics.fmean(found) if found else None,
                               'median_gap': statistics.median(found) if found else None})
    large = groups.get('n>=50', [])
    h1 = [wilcoxon_test(large, 'RL', other, t) for t in H1_BUDGETS for other in ('IGA', 'SA', 'GA')]
    h2 = [wilcoxon_test(large, 'RL', other, t) for t in H2_BUDGETS for other in ('IGA', 'SA')]
    # Exploratory, added after the pre-registered results were seen (reported separately as post hoc).
    exploratory = [wilcoxon_test(groups[g], method, other, t)
                   for g in ('n50', 'n100') if g in groups for t in (0.2, 0.5, 1.0, 2.0)
                   for method, other in (('RL', 'IGA'), ('RL', 'SA'), ('RL-cpu', 'IGA'))]
    pairs = {}
    for r in rows:
        pairs.setdefault(r['case_id'], {})[r['mode']] = r
    h3 = {}
    for factor in ('num_tasks', 'profile', 'alpha_percent', 'beta_percent', 'tau_percent'):
        for level in sorted({r[factor] for r in rows}, key=str):
            chosen = [p for p in pairs.values() if p['fixed'][factor] == level]
            gains = [(p['fixed']['best_known'] - p['joint']['best_known']) / p['fixed']['best_known']
                     for p in chosen if p['fixed']['best_known'] > 0]
            h3[f'{factor}={level}'] = {
                'pairs': len(chosen), 'fixed_positive': len(gains),
                'mean_relative_reduction': statistics.fmean(gains) if gains else None,
                'joint_better': sum(p['joint']['best_known'] < p['fixed']['best_known'] for p in chosen),
                'joint_worse': sum(p['joint']['best_known'] > p['fixed']['best_known'] for p in chosen)}
    write_csv(args.output_dir / 'curves.csv', curves)
    write_json(args.output_dir / 'summary.json', {
        'experiment': 'g9_g4_summary', 'instances': len(rows), 'budgets': BUDGETS, 'methods': METHODS,
        'H1_rl_vs_search_short_budgets_n_ge_50': h1, 'H2_rl_vs_search_long_budgets_n_ge_50': h2,
        'H3_joint_vs_fixed_on_best_known': h3,
        'exploratory_post_hoc_by_size': [{'group': g, **t} for g, t in zip(
            [g for g in ('n50', 'n100') if g in groups for _ in range(12)], exploratory)],
        'inputs_sha256': {str(path / 'rows.jsonl'): sha256(path / 'rows.jsonl') for path in [*args.search, args.policy]},
        **prov})
    plot(curves, args.output_dir / 'curves.png')
    for test in h1:
        if not test['instances']:
            continue
        LOGGER.info('H1 t=%s RL vs %s: gap %.4f vs %.4f, W/T/L %d/%d/%d, p=%s, RL coverage %.2f', test['budget'],
                    test['other'], test['mean_gap_method'] or float('nan'), test['mean_gap_other'] or float('nan'),
                    test['wins'], test['ties'], test['losses'], test['wilcoxon_p'], test['method_coverage'])
    return 0


def plot(curves: list[dict], path: Path) -> None:
    """Mean gap (log scale) vs time budget; hollow markers where a method covers < 100% of instances."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    styles = {'MDD': ('tab:gray', '--'), 'GA': ('tab:orange', '-'), 'SA': ('tab:green', '-'), 'IGA': ('tab:red', '-'),
              'CP-SAT': ('tab:purple', ':'), 'RL': ('tab:blue', '-'), 'RL-cpu': ('tab:cyan', '--')}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, group in zip(axes, ('n20', 'n50', 'n100')):
        for method, (color, line) in styles.items():
            points = [(c['budget'], c['mean_gap'], c['coverage']) for c in curves
                      if c['group'] == group and c['method'] == method and c['mean_gap']]
            if not points:
                continue
            ax.plot([b for b, _, _ in points], [g for _, g, _ in points], line, color=color, label=method)
            for b, g, coverage in points:
                ax.plot(b, g, 'o', color=color, markerfacecolor=color if coverage == 1.0 else 'white')
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_title(group.replace('n', 'n = '))
        ax.set_xlabel('time budget per instance (s)')
        ax.grid(True, which='both', alpha=0.3)
    axes[0].set_ylabel('mean gap to best known (log)')
    axes[-1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    raise SystemExit(main())
