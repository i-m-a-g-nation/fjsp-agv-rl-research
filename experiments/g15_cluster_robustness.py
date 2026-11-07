"""Cluster-level robustness of the pre-registered tests (G4, G5, L2) and Holm correction for G4.

Exploratory re-analysis added after all results were seen (2026-11-07). It only
reads archived result rows; nothing is solved, trained or timed.

Why: the test instances share base data. In G4/G5 the processing times and
due-date quantiles depend only on (n, instance seed); every case of the factor
grid with that pair (and both maintenance modes) reuses them. In L2 each
benchmark instance appears in 5 configurations. The archived Wilcoxon tests
treat every instance as independent.

Per pre-registered test (and training seed):
* instance level: the archived test, recomputed from the rows and checked
  against the archived summary (the run stops if they differ);
* cluster level: clusters are (n, instance seed) for G4/G5 and the benchmark
  instance for L2. Exact sign-flip permutation test on the cluster means of the
  paired differences, one-sided in the registered direction. With k clusters
  p cannot go below 2**-k, so with few clusters no test can reach 0.05.
  Holm within each training seed over the study's tests, as in G5/L2; a
  hypothesis holds if it holds for at least 2 of the 3 seeds.
G4 only: one-sided instance-level Wilcoxon in the registered direction with
Holm within H1 (alpha 0.01, as registered) and within H2 (alpha 0.05, no
threshold registered); Holm over the 24 post-hoc two-sided tests.

Input: ``--results-dir`` holding the archived g4_*, g5_* and l2_formal_test
directories. Writes summary.json, tests.csv and clusters.csv.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
import statistics

from _common import (ROOT, cluster_sign_flip, holm_adjust, parse_args, provenance, read_csv, sha256, write_csv,
                     write_json)
import g9_g4_summary as g9
import g12_g5_summary as g12

LOGGER = logging.getLogger(__name__)
G4_SEARCH = ('g4_search_curves', 'g4_search_curves_retimed')
G4_POLICY = 'g4_policy_curves'
G5_SEARCH = ('g5_search_curves', 'g5_search_curves_large')
G5_RUNS = {kind: [f'{prefix}_seed{s}{suffix}' for s in g12.SEEDS for suffix in ('', '_large')]
           for kind, prefix in (('rl', 'g5_policy_curves'), ('bc', 'g5_bc_curves'), ('seeded', 'g5_seeded_iga'))}
L2_TESTS = {'H1': ('greedy', 'EFT', ('T1', 'T2')), 'H2': ('sample32', 'best_rule', ('T1', 'T2')),
            'H3': ('sample32', 'sa_equal_time', ('T2',)), 'H4': ('sample32', 'sa_equal_time', ('T1',))}
ALPHA, G4_H1_ALPHA = 0.05, 0.01


def wilcoxon_p(diffs: list[float], alternative: str = 'two-sided'):
    from scipy.stats import wilcoxon

    nonzero = [d for d in diffs if d != 0]
    return float(wilcoxon(nonzero, alternative=alternative).pvalue) if nonzero else 1.0


def same(recomputed, archived, what: str) -> None:
    if archived is None and recomputed is None:
        return
    if archived is None or recomputed is None or not math.isclose(recomputed, archived, rel_tol=1e-9, abs_tol=0.0):
        raise ValueError(f'{what}: recomputed {recomputed} differs from archived {archived}')


def counts(diffs: list[float]) -> dict:
    return {'instances': len(diffs), 'wins': sum(d < 0 for d in diffs), 'ties': sum(d == 0 for d in diffs),
            'losses': sum(d > 0 for d in diffs)}


def cluster_rows(study: str, test: dict, groups: dict) -> list[dict]:
    keys = ('study', 'hypothesis', 'training_seed', 'budget', 'method', 'other')
    return [{**{k: test.get(k) for k in keys}, 'cluster': cluster, **counts(d),
             'mean_difference': statistics.fmean(d)} for cluster, d in sorted(groups.items(), key=str)]


def gap_diffs(rows: list[dict], method: str, other: str, t: float) -> tuple[list[dict], list[float]]:
    both = [r for r in rows if r['values'][t][method] is not None and r['values'][t][other] is not None]
    return both, [r['gap'][t][method] - r['gap'][t][other] for r in both]


def flip(groups: dict, direction: str) -> dict:
    """Cluster test without the per-cluster means; a test with nothing to compare cannot support anything (p = 1)."""
    if not groups:
        return {'clusters': 0, 'clusters_favouring': 0, 'clusters_against': 0, 'p_cluster': 1.0, 'p_cluster_min': 1.0}
    return {k: v for k, v in cluster_sign_flip(groups, direction).items() if k != 'cluster_means'}


def by_workload(rows: list[dict], diffs: list[float]) -> dict:
    groups = {}
    for r, d in zip(rows, diffs):
        groups.setdefault(f"n{r['num_tasks']}-s{r['instance_seed']}", []).append(d)
    return groups


def g4_tests(results: Path) -> tuple[list[dict], list[dict]]:
    rows = g9.build_rows([results / d for d in G4_SEARCH], results / G4_POLICY)
    archived = json.loads((results / 'g4_summary/summary.json').read_text(encoding='utf-8'))
    large = [r for r in rows if r['num_tasks'] >= 50]
    families = {
        'H1': ([(t, o) for t in g9.H1_BUDGETS for o in ('IGA', 'SA', 'GA')], 'less', G4_H1_ALPHA,
               archived['H1_rl_vs_search_short_budgets_n_ge_50']),
        'H2': ([(t, o) for t in g9.H2_BUDGETS for o in ('IGA', 'SA')], 'greater', ALPHA,
               archived['H2_rl_vs_search_long_budgets_n_ge_50'])}
    tests, clusters = [], []
    for name, (grid, direction, alpha, old) in families.items():
        found = []
        for (t, other), previous in zip(grid, old, strict=True):
            both, diffs = gap_diffs(large, 'RL', other, t)
            test = {'study': 'G4', 'hypothesis': name, 'training_seed': 0, 'budget': t, 'method': 'RL',
                    'other': other, 'direction': f'RL - {other} {direction} 0', **counts(diffs)}
            for key in ('wins', 'ties', 'losses'):
                if test[key] != previous[key]:
                    raise ValueError(f'G4 {name} t={t} {other}: {key} differs from the archived summary')
            two_sided = wilcoxon_p(diffs) if sum(d != 0 for d in diffs) >= 10 else None
            same(two_sided, previous['wilcoxon_p'], f'G4 {name} t={t} {other}')
            groups = by_workload(both, diffs)
            test.update({'p_instance_archived_two_sided': two_sided,
                         'p_instance_one_sided': wilcoxon_p(diffs, direction), 'alpha': alpha,
                         **flip(groups, direction)})
            found.append(test)
            clusters += cluster_rows('G4', test, groups)
        for test, adjusted in zip(found, holm_adjust([f['p_instance_one_sided'] for f in found])):
            test.update({'p_instance_holm': adjusted, 'holds_instance_holm': adjusted < test['alpha']})
        for test, adjusted in zip(found, holm_adjust([f['p_cluster'] for f in found])):
            test.update({'p_cluster_holm': adjusted, 'holds_cluster_holm': adjusted < test['alpha']})
        tests += found
    # The 24 post-hoc tests of g9, two-sided as archived, now with Holm over the family.
    groups = {f'n{n}': [r for r in rows if r['num_tasks'] == n] for n in (50, 100)}
    grid = [(g, t, m, o) for g in ('n50', 'n100') for t in (0.2, 0.5, 1.0, 2.0)
            for m, o in (('RL', 'IGA'), ('RL', 'SA'), ('RL-cpu', 'IGA'))]
    found = []
    for (g, t, method, other), previous in zip(grid, archived['exploratory_post_hoc_by_size'], strict=True):
        _, diffs = gap_diffs(groups[g], method, other, t)
        p = wilcoxon_p(diffs) if sum(d != 0 for d in diffs) >= 10 else None
        same(p, previous['wilcoxon_p'], f'G4 post hoc {g} t={t} {method} vs {other}')
        found.append({'study': 'G4', 'hypothesis': f'post-hoc {g}', 'training_seed': 0, 'budget': t,
                      'method': method, 'other': other, 'direction': 'two-sided', **counts(diffs),
                      'p_instance_archived_two_sided': p, 'alpha': ALPHA})
    usable = [f for f in found if f['p_instance_archived_two_sided'] is not None]
    for test, adjusted in zip(usable, holm_adjust([f['p_instance_archived_two_sided'] for f in usable])):
        test.update({'p_instance_holm': adjusted, 'holds_instance_holm': adjusted < ALPHA})
    return tests + found, clusters


def seeded_verdicts(tests: list[dict], study: str, names) -> list[dict]:
    """Holm over the study's cluster-level tests within each training seed; holds if >= 2 of 3 seeds."""
    for seed in g12.SEEDS:
        chosen = [t for t in tests if t['training_seed'] == seed]
        for test, adjusted in zip(chosen, holm_adjust([t['p_cluster'] for t in chosen])):
            test.update({'p_cluster_holm': adjusted, 'holds_cluster_holm': adjusted < ALPHA})
    return [{'study': study, 'hypothesis': name, 'seeds_holding_instance_archived': sum(
                t['holds_instance_archived'] for t in tests if t['hypothesis'] == name),
             'seeds_holding_cluster': sum(t['holds_cluster_holm'] for t in tests if t['hypothesis'] == name)}
            for name in names]


def g5_tests(results: Path) -> tuple[list[dict], list[dict], list[dict]]:
    runs = g12.run_dirs(*([results / d for d in G5_RUNS[kind]] for kind in ('rl', 'bc', 'seeded')))
    rows = g12.build_rows([results / d for d in G5_SEARCH], runs)
    archived = {(h['hypothesis'], h['training_seed']): h for h in
                json.loads((results / 'g5_summary/summary.json').read_text(encoding='utf-8'))['hypotheses']}
    tests, clusters = [], []
    for seed in g12.SEEDS:
        for name, (method, other, _, _, t) in g12.TESTS.items():
            both, ours, theirs = g12.hypothesis_pairs(rows, name, seed)
            diffs = [a - b for a, b in zip(ours, theirs)]
            previous = archived[name, seed]
            recomputed = g12.one_sided(ours, theirs)
            same(recomputed['p_one_sided'], previous['p_one_sided'], f'G5 {name} seed {seed}')
            groups = by_workload(both, diffs)
            test = {'study': 'G5', 'hypothesis': name, 'training_seed': seed, 'budget': t,
                    'method': 'RL greedy' if name == 'H2' else method,
                    'other': 'BC greedy' if name == 'H2' else other, 'direction': 'method - other less 0',
                    **counts(diffs), 'p_instance_one_sided': previous['p_one_sided'],
                    'p_instance_holm': previous['p_holm'], 'holds_instance_archived': previous['holds'], 'alpha': ALPHA,
                    **flip(groups, 'less')}
            tests.append(test)
            clusters += cluster_rows('G5', test, groups)
    return tests, clusters, seeded_verdicts(tests, 'G5', g12.TESTS)


def l2_tests(results: Path) -> tuple[list[dict], list[dict], list[dict]]:
    rows = read_csv(results / 'l2_formal_test/rows.csv')
    archived = {(h['hypothesis'], h['training_seed']): h for h in read_csv(results / 'l2_formal_test/hypotheses.csv')}
    tests, clusters = [], []
    for seed in g12.SEEDS:
        for name, (method, baseline, sets) in L2_TESTS.items():
            group = [r for r in rows if r['test_set'] in sets]
            other = baseline if baseline in ('EFT', 'best_rule') else f'{baseline}_s{seed}'
            diffs = [float(r[f'{method}_s{seed}']) - float(r[other]) for r in group]
            previous = archived[name, str(seed)]
            p = wilcoxon_p(diffs, 'less')
            same(p, float(previous['p_one_sided']), f'L2 {name} seed {seed}')
            groups = {}
            for r, d in zip(group, diffs):
                groups.setdefault(f"{r['test_set']}-{r['instance']}", []).append(d)
            test = {'study': 'L2', 'hypothesis': name, 'training_seed': seed, 'budget': None, 'method': method,
                    'other': baseline, 'direction': 'makespan method - other less 0', **counts(diffs),
                    'p_instance_one_sided': p, 'p_instance_holm': float(previous['p_holm']),
                    'holds_instance_archived': previous['holds'] == 'True', 'alpha': ALPHA,
                    **flip(groups, 'less')}
            tests.append(test)
            clusters += cluster_rows('L2', test, groups)
    return tests, clusters, seeded_verdicts(tests, 'L2', L2_TESTS)


def main() -> int:
    def extra(parser):
        parser.add_argument('--results-dir', type=Path, default=ROOT / 'experiments' / 'results',
                            help='directory holding the archived g4_*, g5_* and l2_formal_test results')

    args = parse_args(__doc__.splitlines()[0], 'g15_cluster_robustness', extra)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)
    results = args.results_dir
    g4, g4_clusters = g4_tests(results)
    g5, g5_clusters, g5_verdicts = g5_tests(results)
    l2, l2_clusters, l2_verdicts = l2_tests(results)
    tests = g4 + g5 + l2
    inputs = sorted({results / d / 'rows.jsonl' for d in (*G4_SEARCH, G4_POLICY, *G5_SEARCH,
                                                        *(d for paths in G5_RUNS.values() for d in paths))}
                    | {results / 'g4_summary/summary.json', results / 'g5_summary/summary.json',
                       results / 'l2_formal_test/rows.csv', results / 'l2_formal_test/hypotheses.csv'})
    write_csv(args.output_dir / 'tests.csv', tests)
    write_csv(args.output_dir / 'clusters.csv', g4_clusters + g5_clusters + l2_clusters)
    write_json(args.output_dir / 'summary.json', {
        'experiment': 'g15_cluster_robustness', 'post_hoc': True, 'tests': tests,
        'verdicts': g5_verdicts + l2_verdicts,
        'inputs_sha256': {p.relative_to(results).as_posix(): sha256(p) for p in inputs}, **prov})
    for test in tests:
        if 'p_cluster' in test:
            LOGGER.info('%s %s seed %s t=%s %s vs %s: clusters %d (%d favour, %d against), p_cluster=%.4g '
                        '(min %.4g), p_instance_one_sided=%.3g', test['study'], test['hypothesis'],
                        test['training_seed'], test['budget'], test['method'], test['other'], test['clusters'],
                        test['clusters_favouring'], test['clusters_against'], test['p_cluster'],
                        test['p_cluster_min'], test['p_instance_one_sided'])
    for verdict in g5_verdicts + l2_verdicts:
        LOGGER.info('%s', json.dumps(verdict))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
