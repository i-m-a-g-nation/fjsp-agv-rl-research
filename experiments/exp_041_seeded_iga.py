"""Does seeding the improved GA with learned-policy plans help? (G3A grid)

Protocol fixed before the run:
* instances: the 480 G3A instances of exp_038/exp_040;
* seed sources per instance: RL1 = greedy rollout of the final model
  policy_s0; RL9 = greedy + 8 sampled rollouts (sampling seed 0, as in
  exp_037); RULE9 = the 9-rule portfolio (control with the same number of
  seeds, no learning);
* variants: IGA (no extra seeds), IGA+RL1, IGA+RL9, IGA+RULE9; budgets 1 000
  and 10 000 decodes (seed decodes included); search seeds 0-4;
* time per variant = seed generation (once per instance) + search;
* headline comparisons: IGA+RL9 vs IGA and vs IGA+RULE9 at equal budget;
  IGA+RL9 at 1 000 vs IGA at 10 000 (similar total time); IGA+RL1 vs IGA
  at 1 000;
* every plan is G1-checked; a value below a proven optimum stops the run.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
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

import numpy as np

from experiments.exp_037_sampling_decoding import load_policies, paired
from src.graduation.dispatch_rules import RULE_PORTFOLIO, solve_dispatch_rule
from src.graduation.metaheuristics import solve_metaheuristic
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data
from src.graduation.scoring_policy import run_episode
from src.graduation.seeded_search import decoded_value, plan_to_sequence, solve_seeded_iga

LOGGER = logging.getLogger(__name__)
EXP_040_RAW = ROOT / 'experiments/results/exp_040_metaheuristics_v1/rows.csv'
PROTOCOL = {
    'instances': 'G3A grid of exp_038/exp_040: 240 pairs x fixed/joint',
    'policy': 'policy_s0 (exp_038 final model, hash-checked checkpoint)',
    'rl_samples': 8,
    'rl_sampling_seed': 0,
    'variants': ['IGA', 'IGA+RL1', 'IGA+RL9', 'IGA+RULE9'],
    'budgets': [1000, 10000],
    'seeds': [0, 1, 2, 3, 4],
    'parallel_processes': 4,
}
SOURCES = ('src/graduation/seeded_search.py', 'src/graduation/metaheuristics.py',
           'src/graduation/scoring_policy.py', 'experiments/exp_041_seeded_iga.py')
_POLICY = None


def _policy():
    global _POLICY
    if _POLICY is None:
        _POLICY = load_policies()['policy_s0']
    return _POLICY


def seed_plans(data, mode: str, protocol: dict) -> tuple[dict, dict]:
    """Seed sequences per source, their decoded values and generation time."""
    policy, started = _policy(), time.perf_counter()
    rl = [run_episode(policy, data, mode=mode)]
    rng = np.random.default_rng(protocol['rl_sampling_seed'])
    rl += [run_episode(policy, data, mode=mode, rng=rng) for _ in range(protocol['rl_samples'])]
    rl_seconds = time.perf_counter() - started
    started = time.perf_counter()
    rules = [solve_dispatch_rule(data, mode=mode, rule=rule, atc_k=k) for rule, k in RULE_PORTFOLIO]
    rule_seconds = time.perf_counter() - started
    sources = {'RL1': [rl[0].result], 'RL9': [e.result for e in rl], 'RULE9': rules}
    seconds = {'RL1': rl_seconds / len(rl), 'RL9': rl_seconds, 'RULE9': rule_seconds}
    plans = {}
    for name, results in sources.items():
        sequences = [plan_to_sequence(r, data) for r in results]
        plans[name] = {'sequences': sequences,
                       'plan_values': [r.total_tardiness for r in results],
                       'decoded_values': [decoded_value(data, mode, s) for s in sequences]}
    return plans, seconds


def run_instance(job: tuple[dict, str, dict]) -> dict:
    case, mode, protocol = job
    data = _data(case)
    plans, seed_seconds = seed_plans(data, mode, protocol)
    out = {'case_id': case['case_id'], 'mode': mode,
           'rl1_plan': plans['RL1']['plan_values'][0], 'rl9_plan_best': min(plans['RL9']['plan_values']),
           'rule9_plan_best': min(plans['RULE9']['plan_values'])}
    for name in ('RL9', 'RULE9'):
        values = plans[name]
        out[f'{name.lower()}_reproduced'] = sum(p == d for p, d in zip(values['plan_values'], values['decoded_values']))
        out[f'{name.lower()}_seed_count'] = len(values['plan_values'])
    for variant in protocol['variants']:
        source = variant.split('+')[1] if '+' in variant else None
        for budget in protocol['budgets']:
            values, seconds = [], []
            for seed in protocol['seeds']:
                started = time.perf_counter()
                if source is None:
                    outcome = solve_metaheuristic(data, mode=mode, algorithm='IGA', evaluations=budget, seed=seed)
                else:
                    outcome = solve_seeded_iga(data, mode=mode, seeds=plans[source]['sequences'],
                                               evaluations=budget, seed=seed)
                seconds.append(time.perf_counter() - started)
                values.append(outcome.result.total_tardiness)
            name = f'{variant}_{budget}'
            out[name] = statistics.fmean(values)
            out[f'{name}_best'] = min(values)
            out[f'{name}_seconds'] = statistics.fmean(seconds) + (seed_seconds[source] if source else 0.0)
    return out


def summarize(rows: list[dict], protocol: dict) -> dict:
    methods = [f'{v}_{b}' for v in protocol['variants'] for b in protocol['budgets']]
    low, high = protocol['budgets'][0], protocol['budgets'][-1]
    groups = {'all': rows}
    for key in sorted({(r['group'], r['num_tasks'], r['num_machines']) for r in rows}):
        groups[f'{key[0]}/n{key[1]}-m{key[2]}'] = [r for r in rows if (r['group'], r['num_tasks'], r['num_machines']) == key]
    out = {}
    for name, selected in groups.items():
        comparisons = []
        for budget in protocol['budgets']:
            comparisons += [paired(selected, f'IGA+RL9_{budget}', f'IGA_{budget}'),
                            paired(selected, f'IGA+RL9_{budget}', f'IGA+RULE9_{budget}'),
                            paired(selected, f'IGA+RULE9_{budget}', f'IGA_{budget}'),
                            paired(selected, f'IGA+RL1_{budget}', f'IGA_{budget}')]
        comparisons.append(paired(selected, f'IGA+RL9_{low}', f'IGA_{high}'))
        out[name] = {
            'instances': len(selected),
            'mean': {m: statistics.fmean(r[m] for r in selected) for m in methods},
            'mean_gap_to_best_known': {m: statistics.fmean(r[m] - r['best_known'] for r in selected) for m in methods},
            'best_known_hits': {m: sum(r[m] == r['best_known'] for r in selected) for m in methods},
            'mean_seconds': {m: statistics.fmean(r[f'{m}_seconds'] for r in selected) for m in methods},
            'seed_plans': {c: statistics.fmean(r[c] for r in selected)
                           for c in ('rl1_plan', 'rl9_plan_best', 'rule9_plan_best')},
            'seed_reproduction_rate': {
                s: sum(r[f'{s}_reproduced'] for r in selected) / sum(r[f'{s}_seed_count'] for r in selected)
                for s in ('rl9', 'rule9')},
            'paired': comparisons,
        }
    return out


def build_rows(results: list[dict], protocol: dict) -> list[dict]:
    with open(EXP_040_RAW, encoding='utf-8', newline='') as handle:
        archived = {(r['case_id'], r['mode']): r for r in csv.DictReader(handle)}
    rows = []
    for result in results:
        old = archived[(result['case_id'], result['mode'])]
        for mine, theirs in (('rl1_plan', 'policy_s0_r1'), ('rl9_plan_best', 'policy_s0_r9'),
                             ('rule9_plan_best', 'best_of_9_rules')):
            if result[mine] != int(old[theirs]):
                raise ValueError(f'{result["case_id"]}/{result["mode"]}: {mine} {result[mine]} != archived {theirs}')
        row = {'case_id': result['case_id'], 'mode': result['mode'], 'group': old['group'],
               'num_tasks': int(old['num_tasks']), 'num_machines': int(old['num_machines']),
               'best_known_exp_040': int(old['best_known']),
               'best_known_proven_optimal': old['best_known_proven_optimal'] == 'True'}
        row.update({k: v for k, v in result.items() if k not in ('case_id', 'mode')})
        best = min([result[f'{v}_{b}_best'] for v in protocol['variants'] for b in protocol['budgets']]
                   + [result['rl9_plan_best'], result['rule9_plan_best']])
        if row['best_known_proven_optimal'] and best < row['best_known_exp_040']:
            raise ValueError(f'{row["case_id"]}/{row["mode"]}: value {best} beats a proven optimum')
        row['best_known'] = min(row['best_known_exp_040'], best)
        rows.append(row)
    return rows


def run_experiment(output_dir: Path, protocol: dict = PROTOCOL, cases: list[dict] | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    cases = build_main_cases() if cases is None else cases
    jobs = [(case, mode, protocol) for case in cases for mode in ('fixed', 'joint')]
    LOGGER.info('seeded IGA: %d instances', len(jobs))
    with ProcessPoolExecutor(max_workers=protocol['parallel_processes']) as pool:
        results = list(pool.map(run_instance, jobs))
    rows = build_rows(results, protocol)
    manifest = {
        'experiment': 'exp_041_seeded_iga',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'protocol': protocol,
        'instances': len(rows),
        'new_best_known': sum(r['best_known'] < r['best_known_exp_040'] for r in rows),
        'summary': summarize(rows, protocol),
        'all_plans_g1_checked': True,
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'research_status': 'not_achieved',
        'environment': {
            'python': platform.python_version(), 'platform': platform.platform(),
            'numpy': importlib.metadata.version('numpy'), 'scipy': importlib.metadata.version('scipy'),
            'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                         text=True, check=False).stdout.strip(),
        },
        'archived_input_sha256': {'experiments/results/exp_040_metaheuristics_v1/rows.csv':
                                  hashlib.sha256(EXP_040_RAW.read_bytes()).hexdigest()},
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    }
    with open(output_dir / 'rows.csv', 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n',
                                              encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'experiments' / 'runs' / 'exp_041_seeded_iga')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    manifest = run_experiment(args.output_dir)
    LOGGER.info('done: %d new best-known, %.1f s', manifest['new_best_known'], manifest['elapsed_seconds'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
