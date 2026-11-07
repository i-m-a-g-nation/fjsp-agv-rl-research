"""Graduation G5: sensitivity of H1, H3, H4 and H5 to a faster IGA (exploratory, after g13).

g13 suggests the G5 IGA runs were up to about 1.6 times slower than the G4
re-timed ones, while RL inference times were unchanged. This script repeats the
G5 tests with every CPU search time divided by a speed factor f (IGA traces;
for RL + IGA only the IGA part after the RL seconds), RL GPU times unchanged:
IGA's value at budget t becomes its recorded value at f * t. best-known and the
test rules are those of g12 (one-sided Wilcoxon on nonzero differences, Holm
within each seed over H1-H5, H2 unchanged since it has no time budget).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from _common import parse_args, provenance, sha256, write_json
from g9_g4_summary import policy_points, read_jsonl, value_at
from g12_g5_summary import SEEDS, all_values, holm, one_sided

LOGGER = logging.getLogger(__name__)
DEFAULT_RESULTS = Path(__file__).resolve().parent / 'results'
FACTORS = (1.0, 1.3, 1.6, 2.0)
TESTS = {'H1': ('RL', 'g5', 100, 1.0), 'H3': ('RL+IGA', 'g5', None, 10.0),
         'H4': ('RL+IGA', 'g5', None, 1.0), 'H5': ('RL', 'g5-large', None, 2.0)}
DIRS = {'g5': ('g5_search_curves', 'g5_policy_curves_seed{}', 'g5_bc_curves_seed{}', 'g5_seeded_iga_seed{}'),
        'g5-large': ('g5_search_curves_large', 'g5_policy_curves_seed{}_large', 'g5_bc_curves_seed{}_large',
                     'g5_seeded_iga_seed{}_large')}


def iga_at(trace: list, t: float, factor: float):
    found = [value for seconds, _, value in trace if seconds <= t * factor]
    return min(found) if found else None


def seeded_at(row: dict, t: float, factor: float):
    """RL + IGA: the RL part keeps its GPU time; only the IGA part after it runs `factor` times faster."""
    rl = row['rl_seconds']
    found = [value for seconds, _, value in row['RL+IGA']['trace'] if seconds <= rl + (t - rl) * factor]
    return min(found) if found else None


def load(results: Path, grid: str) -> list[dict]:
    search_dir, rl_dir, bc_dir, seeded_dir = DIRS[grid]
    search = read_jsonl(results / search_dir / 'rows.jsonl')
    rl = {s: read_jsonl(results / rl_dir.format(s) / 'rows.jsonl') for s in SEEDS}
    bc = {s: read_jsonl(results / bc_dir.format(s) / 'rows.jsonl') for s in SEEDS}
    seeded = {s: read_jsonl(results / seeded_dir.format(s) / 'rows.jsonl') for s in SEEDS}
    rows = []
    for key, s in search.items():
        candidates = all_values(s)
        for seed in SEEDS:
            for policy in (rl[seed][key], bc[seed][key]):
                candidates += [v for part in ('device', 'cpu') for _, v in policy_points(policy[part])]
            candidates.append(seeded[seed][key]['RL+IGA']['value'])
        rows.append({'grid': grid, 'num_tasks': s['num_tasks'], 'search': s, 'bk': min(candidates),
                     'rl': {seed: rl[seed][key] for seed in SEEDS}, 'seeded': {seed: seeded[seed][key] for seed in SEEDS}})
    return rows


def main() -> int:
    def extra(parser):
        parser.add_argument('--results-dir', type=Path, default=DEFAULT_RESULTS,
                            help='directory holding the archived g5_* runs and g5_summary')

    args = parse_args(__doc__.splitlines()[0], 'g14_g5_iga_speed_sensitivity', extra)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)
    results_dir = args.results_dir
    h2_p = load_h2_p(results_dir)
    rows = load(results_dir, 'g5') + load(results_dir, 'g5-large')
    gap = lambda value, bk: (value - bk) / max(1, bk)
    results = []
    for factor in FACTORS:
        for seed in SEEDS:
            found = []
            for name, (method, grid, size, t) in TESTS.items():
                ours, theirs = [], []
                for r in rows:
                    if r['grid'] != grid or (size is not None and r['num_tasks'] != size):
                        continue
                    a = (value_at(r['search'], r['rl'][seed], 'RL', t) if method == 'RL'
                         else seeded_at(r['seeded'][seed], t, factor))
                    b = iga_at(r['search']['IGA']['trace'], t, factor)
                    if a is not None and b is not None:
                        ours.append(gap(a, r['bk']))
                        theirs.append(gap(b, r['bk']))
                found.append({'factor': factor, 'hypothesis': name, 'training_seed': seed, **one_sided(ours, theirs)})
            # H2 has no time budget; its Holm-adjusted p is taken from the archived g12 run.
            found.append({'factor': factor, 'hypothesis': 'H2', 'training_seed': seed, 'p_one_sided': h2_p[seed]})
            holm(found)
            results += [item for item in found if item['hypothesis'] != 'H2']
    for factor in FACTORS:
        held = {name: sum(r['holds'] for r in results if r['factor'] == factor and r['hypothesis'] == name)
                for name in TESTS}
        LOGGER.info('factor %.1f: seeds holding %s', factor, held)
    with open(args.output_dir / 'tests.jsonl', 'w', encoding='utf-8', newline='\n') as handle:
        for item in results:
            handle.write(json.dumps(item, separators=(',', ':')) + '\n')
    inputs = sorted({results_dir / d.format(s) / 'rows.jsonl' for dirs in DIRS.values() for d in dirs for s in SEEDS})
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g14_g5_iga_speed_sensitivity', 'factors': FACTORS, 'tests': TESTS,
        'h2_p_one_sided_from_g12': h2_p,
        'inputs_sha256': {str(p.relative_to(results_dir.parent)): sha256(p) for p in inputs}, **prov})
    return 0


def load_h2_p(results: Path) -> dict:
    """H2's one-sided p per training seed from the archived g12 run (H2 has no time budget)."""
    with open(results / 'g5_summary' / 'summary.json', encoding='utf-8') as handle:
        tests = json.load(handle)['hypotheses']
    return {t['training_seed']: t['p_one_sided'] for t in tests if t['hypothesis'] == 'H2'
            and t['training_seed'] != 'all'}


if __name__ == '__main__':
    raise SystemExit(main())
