"""Re-check the exp_037/038 rule baselines with the literature ATC look-ahead k=2.

exp_036-038 used ATC with k=1 for the single ATC rule and for "best of
EDD/MDD/ATC". Vepsalainen & Morton (1987) recommend k=2 for static shops
(1.5-4.5 in general), so those two baselines may be too weak. Protocol fixed
before the run:

* instances: the exp_037 test split (600) and the G3A grid used by exp_038
  (480), regenerated from their archived generators;
* all nine portfolio rules are rerun and every plan is G1-checked; EDD, MDD,
  ATC k=1 and the 9-rule best must equal the archived values, otherwise the
  run stops;
* policy values are read from the archived rows (not rerun);
* new baselines: ATC k=2 (single rule) and best of EDD/MDD/ATC k=2; ATC k=3
  is reported as sensitivity only. The 9-rule portfolio already contains
  k=2 and k=3, so its comparison is unchanged.
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

from experiments.exp_037_sampling_decoding import _checked, paired
from experiments.exp_038_g3b_comparison import g3_instances
from src.graduation.dispatch_rules import RULE_PORTFOLIO, solve_dispatch_rule
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.scoring_training import Instance, make_instances

LOGGER = logging.getLogger(__name__)
TEST_RAW = ROOT / 'experiments/results/exp_037_sampling_decoding_v1/test_rows.csv'
G3_RAW = ROOT / 'experiments/results/exp_038_g3b_comparison_v1/rows.csv'
PROTOCOL = {
    'test': {'seeds': [40000, 40600], 'sampler_seed': 4, 'balanced': True},
    'standard_atc_k': 2.0,
    'sensitivity_atc_k': 3.0,
    'policies': ['policy_s0', 'policy_s1', 'policy_s2'],
    'final_model': 'policy_s0',
    'comparisons': {'r1': ['MDD', 'ATC_k2'], 'r3': ['best_of_3_rules', 'best_of_3_rules_k2'],
                    'r9': ['best_of_9_rules']},
}
FACTORS = ('seed', 'num_tasks', 'num_machines', 'alpha_percent', 'beta_percent', 'tau_percent', 'mode')
ARCHIVED_RULES = ('EDD', 'MDD', 'ATC', 'best_of_9_rules')
SOURCES = ('src/graduation/dispatch_rules.py', 'experiments/exp_037_sampling_decoding.py',
           'experiments/exp_038_g3b_comparison.py', 'experiments/exp_039_atc_k2_baseline.py')


def _label(rule: str, k: float) -> str:
    return rule if rule != 'ATC' else f'ATC_k{k:g}'


def rule_values(instance: Instance) -> dict[str, int]:
    """All nine portfolio rules on one instance, each plan G1-checked."""
    return {_label(rule, k): _checked(solve_dispatch_rule(instance.data, mode=instance.mode, rule=rule, atc_k=k),
                                      instance)
            for rule, k in RULE_PORTFOLIO}


def build_rows(instances: list[Instance], archived: list[dict], keys: list[dict],
               protocol: dict = PROTOCOL) -> list[dict]:
    """Rerun rules, verify them against the archived rows and attach archived policy values."""
    k2, k3 = _label('ATC', protocol['standard_atc_k']), _label('ATC', protocol['sensitivity_atc_k'])
    rows = []
    for instance, old, extra in zip(instances, archived, keys, strict=True):
        values = rule_values(instance)
        rerun = {'EDD': values['EDD'], 'MDD': values['MDD'], 'ATC': values['ATC_k1'],
                 'best_of_9_rules': min(values.values())}
        for column in ARCHIVED_RULES:
            if rerun[column] != int(old[column]):
                raise ValueError(f'{column} rerun {rerun[column]} != archived {old[column]} for {extra}')
        row = {**extra, **{f: instance_factor(instance, f) for f in FACTORS}, **rerun,
               'ATC_k2': values[k2], 'ATC_k3': values[k3],
               'best_of_3_rules': min(rerun['EDD'], rerun['MDD'], rerun['ATC']),
               'best_of_3_rules_k2': min(rerun['EDD'], rerun['MDD'], values[k2])}
        for name in protocol['policies']:
            for budget in ('1', '3', '9'):
                row[f'{name}_r{budget}'] = int(old[f'{name}_r{budget}'])
        rows.append(row)
    return rows


def instance_factor(instance: Instance, factor: str):
    return instance.seed if factor == 'seed' else getattr(instance, factor)


def summarize(rows: list[dict], group_keys: tuple[str, ...], protocol: dict = PROTOCOL) -> dict:
    groups = {'all': rows}
    for key in sorted({tuple(r[k] for k in group_keys) for r in rows}):
        groups['/'.join(f'{k}={v}' for k, v in zip(group_keys, key))] = [
            r for r in rows if tuple(r[k] for k in group_keys) == key]
    rules = ('EDD', 'MDD', 'ATC', 'ATC_k2', 'ATC_k3', 'best_of_3_rules', 'best_of_3_rules_k2', 'best_of_9_rules')
    out = {}
    for name, selected in groups.items():
        out[name] = {
            'instances': len(selected),
            'rule_means': {c: statistics.fmean(r[c] for r in selected) for c in rules},
            'rule_vs_rule': [paired(selected, 'ATC_k2', 'ATC'), paired(selected, 'ATC_k2', 'MDD'),
                             paired(selected, 'best_of_3_rules_k2', 'best_of_3_rules')],
            'policy_vs_rule': [paired(selected, f'{policy}_{budget}', baseline)
                               for policy in protocol['policies']
                               for budget, baselines in protocol['comparisons'].items()
                               for baseline in baselines],
        }
    return out


def _read(path: Path) -> list[dict]:
    with open(path, encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_split(protocol: dict = PROTOCOL, limit: int | None = None) -> list[dict]:
    spec = protocol['test']
    instances = make_instances(range(*spec['seeds']), sampler_seed=spec['sampler_seed'], balanced=spec['balanced'])
    archived = _read(TEST_RAW)
    if len(instances) != len(archived):
        raise ValueError('exp_037 test split size does not match the archived rows')
    for instance, old in zip(instances, archived):
        if any(str(instance_factor(instance, f)) != old[f] for f in FACTORS):
            raise ValueError(f'exp_037 instance order differs at seed {old["seed"]}')
    pairs = list(zip(instances, archived))[:limit]
    return build_rows([p[0] for p in pairs], [p[1] for p in pairs], [{} for _ in pairs], protocol)


def g3_grid(protocol: dict = PROTOCOL, limit: int | None = None) -> list[dict]:
    instances, keys = g3_instances(build_main_cases())
    archived = {(r['case_id'], r['mode']): r for r in _read(G3_RAW)}
    if len(archived) != len(instances):
        raise ValueError('exp_038 row count does not match the G3A grid')
    selected = list(zip(instances, keys))[:limit]
    return build_rows([s[0] for s in selected], [archived[(s[1][0], s[1][2])] for s in selected],
                      [{'case_id': s[1][0], 'group': s[1][1]} for s in selected], protocol)


def run_experiment(output_dir: Path, protocol: dict = PROTOCOL, limit: int | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    test_rows = test_split(protocol, limit)
    g3_rows = g3_grid(protocol, limit)
    manifest = {
        'experiment': 'exp_039_atc_k2_baseline',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'protocol': protocol,
        'instances': {'exp_037_test': len(test_rows), 'g3_grid': len(g3_rows)},
        'archived_rules_reproduced': list(ARCHIVED_RULES),
        'exp_037_test_summary': summarize(test_rows, ('num_tasks', 'num_machines'), protocol),
        'g3_summary': summarize(g3_rows, ('group', 'num_tasks', 'num_machines'), protocol),
        'all_plans_g1_checked': True,
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'research_status': 'not_achieved',
        'environment': {
            'python': platform.python_version(), 'platform': platform.platform(),
            'scipy': importlib.metadata.version('scipy'),
            'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                         text=True, check=False).stdout.strip(),
        },
        'archived_input_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in (TEST_RAW, G3_RAW)},
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    }
    for name, rows in (('exp_037_test_rows.csv', test_rows), ('g3_rows.csv', g3_rows)):
        with open(output_dir / name, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n',
                                              encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'experiments' / 'runs' / 'exp_039_atc_k2_baseline')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    manifest = run_experiment(args.output_dir)
    LOGGER.info('done in %.1f s', manifest['elapsed_seconds'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
