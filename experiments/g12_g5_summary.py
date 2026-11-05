"""Graduation G5: curves, the pre-registered tests H1-H5 and descriptive results.

docs/protocols/g5_supplement_protocol.md. Inputs, each a run directory:
``--search`` (g7 on ``g5``, then on ``g5-large``), ``--rl`` / ``--bc`` /
``--seeded`` (per training seed s = 0, 1, 2 and per grid: g8 with the best
checkpoint, g8 with the imitation-only checkpoint, g11). Values at a time
budget follow g9_g4_summary (``value_at``); RL+IGA takes the best point of its
shifted trace within t. best_known = minimum over every method, seed and run;
gap = (T - best_known) / max(1, best_known).

Hypotheses, per training seed (one-sided paired Wilcoxon on the gaps, zero
differences dropped, Holm over H1-H5 within the seed; a hypothesis holds if
it holds for at least 2 of the 3 seeds):
H1 RL < IGA on G5-T, n = 100, t = 1 s;  H2 RL greedy T < imitation-only greedy T
on G5-T;  H3 RL+IGA < IGA on G5-T, t = 10 s;  H4 the same at t = 1 s;
H5 RL < IGA on G5-L, t = 2 s. Writes summary.json, curves.csv, curves.png.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import statistics

from _common import parse_args, provenance, sha256, write_csv, write_json
from g9_g4_summary import BUDGETS, policy_points, read_jsonl, value_at

LOGGER = logging.getLogger(__name__)
SEEDS = (0, 1, 2)
SEARCH = ('MDD', 'ATC', 'EDD', 'SA', 'IGA', 'CP-SAT')
TESTS = {'H1': ('RL', 'IGA', 'g5', 100, 1.0), 'H2': ('RL-greedy', 'BC-greedy', 'g5', None, None),
         'H3': ('RL+IGA', 'IGA', 'g5', None, 10.0), 'H4': ('RL+IGA', 'IGA', 'g5', None, 1.0),
         'H5': ('RL', 'IGA', 'g5-large', None, 2.0)}


def search_values(row: dict, t: float) -> dict:
    values = {}
    for method in SEARCH:
        if method == 'CP-SAT' and method not in row:
            values[method] = None
        else:
            values[method] = value_at(row, {}, method, t)
    return values


def trace_value(trace: list, t: float):
    found = [value for seconds, _, value in trace if seconds <= t]
    return min(found) if found else None


def all_values(row: dict) -> list[int]:
    """Every final value one search row contains (for best_known)."""
    values = [row[r]['value'] for r in ('MDD', 'ATC', 'EDD')] + [row['IGA']['value']]
    values += [run['value'] for run in row['SA'].values()]
    if row.get('CP-SAT', {}).get('value') is not None:
        values.append(row['CP-SAT']['value'])
    return values


def holm(tests: list[dict]) -> None:
    ordered = sorted(tests, key=lambda item: item['p_one_sided'])
    running = 0.0
    for rank, item in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * item['p_one_sided']))
        item['p_holm'] = running
        item['holds'] = running < 0.05


def one_sided(ours: list[float], theirs: list[float]) -> dict:
    from scipy.stats import wilcoxon

    diffs = [a - b for a, b in zip(ours, theirs)]
    nonzero = [d for d in diffs if d != 0]
    p = float(wilcoxon(nonzero, alternative='less').pvalue) if nonzero else 1.0
    return {'compared': len(diffs), 'wins': sum(d < 0 for d in diffs), 'ties': sum(d == 0 for d in diffs),
            'losses': sum(d > 0 for d in diffs), 'mean_method': statistics.fmean(ours) if ours else None,
            'mean_other': statistics.fmean(theirs) if theirs else None, 'p_one_sided': p}


def main() -> int:
    def extra(parser):
        parser.add_argument('--search', type=Path, nargs=2, required=True, metavar=('G5', 'G5_LARGE'))
        for name in ('rl', 'bc', 'seeded'):
            parser.add_argument(f'--{name}', type=Path, nargs=6, required=True,
                                metavar=('S0_G5', 'S0_LARGE', 'S1_G5', 'S1_LARGE', 'S2_G5', 'S2_LARGE'))

    args = parse_args(__doc__.splitlines()[0], 'g12_g5_summary', extra)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)
    grids = ('g5', 'g5-large')
    runs = {name: {(s, g): getattr(args, name)[2 * i + j] for i, s in enumerate(SEEDS) for j, g in enumerate(grids)}
            for name in ('rl', 'bc', 'seeded')}
    rows = []
    for j, grid in enumerate(grids):
        search = read_jsonl(args.search[j] / 'rows.jsonl')
        side = {name: {s: read_jsonl(runs[name][s, grid] / 'rows.jsonl') for s in SEEDS} for name in runs}
        for name, by_seed in side.items():
            if any(set(rows_) != set(search) for rows_ in by_seed.values()):
                raise ValueError(f'{name} runs on {grid} cover different instances than the search run')
        for key in sorted(search):
            s = search[key]
            rl = {seed: side['rl'][seed][key] for seed in SEEDS}
            bc = {seed: side['bc'][seed][key] for seed in SEEDS}
            seeded = {seed: side['seeded'][seed][key]['RL+IGA'] for seed in SEEDS}
            candidates = all_values(s)
            for seed in SEEDS:
                for policy in (rl[seed], bc[seed]):
                    candidates += [v for part in ('device', 'cpu') for _, v in policy_points(policy[part])]
                candidates.append(seeded[seed]['value'])
            bk = min(candidates)
            cp = s.get('CP-SAT')
            if cp and cp['value'] is not None and cp['status'] == 'OPTIMAL' and bk < cp['value']:
                raise ValueError(f'{key}: a method beats a proven CP-SAT optimum')
            values = {}
            for t in BUDGETS:
                v = search_values(s, t)
                for seed in SEEDS:
                    v[f'RL_s{seed}'] = value_at(s, rl[seed], 'RL', t)
                    v[f'RL-cpu_s{seed}'] = value_at(s, rl[seed], 'RL-cpu', t)
                    v[f'BC_s{seed}'] = value_at(s, bc[seed], 'RL', t)
                    v[f'RL+IGA_s{seed}'] = trace_value(seeded[seed]['trace'], t)
                values[t] = v
            gap = {t: {m: None if v is None else (v - bk) / max(1, bk) for m, v in values[t].items()} for t in BUDGETS}
            greedy = {f'{kind}_s{seed}': policy[seed]['device']['greedy']['value']
                      for kind, policy in (('RL', rl), ('BC', bc)) for seed in SEEDS}
            sample16 = {f'{kind}_s{seed}': min(policy[seed]['device']['greedy']['value'],
                                                policy[seed]['device']['sample16']['value'])
                        for kind, policy in (('RL', rl), ('BC', bc)) for seed in SEEDS}
            rows.append({**{k: s[k] for k in ('case_id', 'mode', 'num_tasks', 'num_machines', 'profile',
                                                'alpha_percent', 'beta_percent', 'tau_percent')},
                         'grid': grid, 'best_known': bk, 'values': values, 'gap': gap, 'greedy': greedy,
                         'sample16': sample16})

    hypotheses = []
    for seed in SEEDS:
        found = []
        for name, (method, other, grid, size, t) in TESTS.items():
            chosen = [r for r in rows if r['grid'] == grid and (size is None or r['num_tasks'] == size)]
            if name == 'H2':
                ours = [r['greedy'][f'RL_s{seed}'] for r in chosen]
                theirs = [r['greedy'][f'BC_s{seed}'] for r in chosen]
                result = one_sided(ours, theirs)
            else:
                a, b = f'{method}_s{seed}', other
                both = [r for r in chosen if r['gap'][t][a] is not None and r['gap'][t][b] is not None]
                result = one_sided([r['gap'][t][a] for r in both], [r['gap'][t][b] for r in both])
                result['coverage_method'] = (sum(r['gap'][t][a] is not None for r in chosen) / len(chosen)
                                             if chosen else None)
            found.append({'hypothesis': name, 'training_seed': seed, 'instances': len(chosen), **result})
        holm(found)
        hypotheses += found
    for name in TESTS:
        held = sum(h['holds'] for h in hypotheses if h['hypothesis'] == name and h['training_seed'] != 'all')
        hypotheses.append({'hypothesis': name, 'training_seed': 'all', 'seeds_holding': held, 'holds': held >= 2})

    methods = list(SEARCH) + [f'{k}_s{s}' for k in ('RL', 'RL-cpu', 'BC', 'RL+IGA') for s in SEEDS]
    groups = {'g5-all': [r for r in rows if r['grid'] == 'g5'],
              **{f'n{n}': [r for r in rows if r['num_tasks'] == n] for n in (20, 50, 100, 200)}}
    groups = {name: selected for name, selected in groups.items() if selected}
    curves = []
    for group, selected in groups.items():
        for t in BUDGETS:
            for m in methods:
                found = [r['gap'][t][m] for r in selected if r['gap'][t][m] is not None]
                curves.append({'group': group, 'budget': t, 'method': m, 'coverage': len(found) / len(selected),
                               'mean_gap': statistics.fmean(found) if found else None})
    seed_spread = []
    for group in groups:
        for t in BUDGETS:
            for kind in ('RL', 'RL+IGA', 'BC'):
                means = [c['mean_gap'] for c in curves if c['group'] == group and c['budget'] == t
                         and c['method'] in {f'{kind}_s{s}' for s in SEEDS} and c['coverage'] == 1.0]
                if len(means) == len(SEEDS):
                    seed_spread.append({'group': group, 'budget': t, 'method': kind,
                                        'min': min(means), 'max': max(means), 'range': max(means) - min(means)})
    ablation = []
    for group in groups:
        for seed in SEEDS:
            selected = groups[group]
            for point in ('greedy', 'sample16'):
                ablation.append({'group': group, 'training_seed': seed, 'point': point,
                                 'mean_rl': statistics.fmean(r[point][f'RL_s{seed}'] for r in selected),
                                 'mean_bc': statistics.fmean(r[point][f'BC_s{seed}'] for r in selected),
                                 'rl_better': sum(r[point][f'RL_s{seed}'] < r[point][f'BC_s{seed}'] for r in selected),
                                 'bc_better': sum(r[point][f'RL_s{seed}'] > r[point][f'BC_s{seed}'] for r in selected)})
    pairs = {}
    for r in groups['g5-all']:
        pairs.setdefault(r['case_id'], {})[r['mode']] = r
    joint_vs_fixed = {}
    for factor in ('num_tasks', 'beta_percent'):
        for level in sorted({r[factor] for r in groups['g5-all']}):
            chosen = [p for p in pairs.values() if p['fixed'][factor] == level]
            gains = [(p['fixed']['best_known'] - p['joint']['best_known']) / p['fixed']['best_known']
                     for p in chosen if p['fixed']['best_known'] > 0]
            joint_vs_fixed[f'{factor}={level}'] = {
                'pairs': len(chosen), 'fixed_positive': len(gains),
                'mean_relative_reduction': statistics.fmean(gains) if gains else None,
                'joint_better': sum(p['joint']['best_known'] < p['fixed']['best_known'] for p in chosen),
                'joint_worse': sum(p['joint']['best_known'] > p['fixed']['best_known'] for p in chosen)}

    inputs = [*args.search] + [path for name in runs for path in runs[name].values()]
    write_csv(args.output_dir / 'curves.csv', curves)
    write_csv(args.output_dir / 'hypotheses.csv', hypotheses)
    write_json(args.output_dir / 'summary.json', {
        'experiment': 'g12_g5_summary', 'instances': {g: sum(r['grid'] == g for r in rows) for g in grids},
        'budgets': BUDGETS, 'hypotheses': hypotheses, 'seed_spread': seed_spread, 'imitation_ablation': ablation,
        'joint_vs_fixed_on_best_known': joint_vs_fixed,
        'inputs_sha256': {str(path / 'rows.jsonl'): sha256(path / 'rows.jsonl') for path in inputs}, **prov})
    plot(curves, args.output_dir / 'curves.png')
    for h in hypotheses:
        LOGGER.info('%s', json.dumps(h))
    return 0


def plot(curves: list[dict], path: Path) -> None:
    """Mean gap (log scale) vs time budget per size; RL, BC and RL+IGA averaged over the training seeds."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    styles = {'MDD': ('tab:gray', '--'), 'SA': ('tab:green', '-'), 'IGA': ('tab:red', '-'),
              'RL': ('tab:blue', '-'), 'BC': ('tab:cyan', ':'), 'RL+IGA': ('tab:purple', '-')}
    fig, axes = plt.subplots(1, 4, figsize=(19, 4.8), sharey=True)
    for ax, group in zip(axes, ('n20', 'n50', 'n100', 'n200')):
        for method, (color, line) in styles.items():
            names = {method} if method in SEARCH else {f'{method}_s{s}' for s in SEEDS}
            points = []
            for t in BUDGETS:
                chosen = [c for c in curves if c['group'] == group and c['budget'] == t and c['method'] in names]
                if chosen and all(c['mean_gap'] is not None and c['coverage'] == 1.0 for c in chosen):
                    points.append((t, statistics.fmean(c['mean_gap'] for c in chosen)))
            points = [(t, g) for t, g in points if g > 0]
            if points:
                ax.plot([t for t, _ in points], [g for _, g in points], line, marker='o', color=color, label=method)
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_title(group.replace('n', 'n = '))
        ax.set_xlabel('time budget per instance (s)')
        ax.grid(True, which='both', alpha=0.3)
    axes[0].set_ylabel('mean gap to best known (log; full coverage only)')
    axes[-1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    raise SystemExit(main())
