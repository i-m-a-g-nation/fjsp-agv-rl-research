"""Graduation main table: rules vs scoring policy vs metaheuristics vs CP-SAT on the G3A grid.

Inputs are earlier runs (each re-hashed into the manifest):
* ``--cpsat``: g1_cpsat_fixed_vs_joint run with ``--long`` (1 s for all, 60 s for n=24 primary);
* ``--policy``: g2_scoring_policy run (its validation-selected final checkpoint);
* ``--meta``: g3_metaheuristics run.
Rules and the policy are re-run here (timed per instance); none of these
instances was used for training or checkpoint selection. best_known is the
minimum over every method; a value below a proven CP-SAT optimum aborts.
Writes rows.csv and manifest.json (means, gaps, paired tests, joint gain).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import statistics
import time

from _common import checked_tardiness, paired, parse_args, provenance, read_csv, sha256, write_csv, write_json

from fjsp_lab.maintenance.generator import g3a_cases
from fjsp_lab.maintenance.rules import RULE_PORTFOLIO, solve_dispatch_rule
from fjsp_lab.maintenance.scoring_policy import ScoringPolicy, best_of_rollouts

LOGGER = logging.getLogger(__name__)
FACTORS = ('num_tasks', 'num_machines', 'alpha_percent', 'beta_percent', 'tau_percent', 'fixed_policy')
ROLLOUTS = {'r1': 0, 'r3': 2, 'r9': 8}


def add_args(parser) -> None:
    for name in ('cpsat', 'policy', 'meta'):
        parser.add_argument(f'--{name}', type=Path, required=True)


def timed(function):
    started = time.perf_counter()
    value = function()
    return value, time.perf_counter() - started


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g4_comparison', add_args)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    policy_manifest = json.loads((args.policy / 'manifest.json').read_text(encoding='utf-8'))
    final = policy_manifest['final_model']
    policy = ScoringPolicy.load(args.policy / 'checkpoints' / f'{final}.npz',
                                expected_sha256=policy_manifest['checkpoint_sha256'][final])
    cpsat = {}
    for row in read_csv(args.cpsat / 'rows.csv'):
        if row['status'] != 'ACCEPTED':
            raise ValueError(f'CP-SAT reference missing for {row["case_id"]}/{row["mode"]}')
        cpsat[row['case_id'], row['mode'], row['setting']] = row
    meta = {(r['case_id'], r['mode']): r for r in read_csv(args.meta / 'rows.csv')}
    meta_methods = [c for c in next(iter(meta.values())) if c not in ('case_id', 'mode')
                    and not c.endswith(('_best', '_worst', '_seconds'))]
    rows = []
    for case in g3a_cases():
        for mode in ('fixed', 'joint'):
            row = {'case_id': case.case_id, 'group': case.group, 'mode': mode, **{f: getattr(case, f) for f in FACTORS}}
            seconds = {}
            portfolio = {}
            for rule, k in RULE_PORTFOLIO:
                plan, spent = timed(lambda: solve_dispatch_rule(case.data, mode=mode, rule=rule, atc_k=k))
                portfolio[rule if rule != 'ATC' else f'ATC_k{k:g}'] = checked_tardiness(plan, case.data, mode)
                seconds[rule] = seconds.get(rule, 0.0) + spent
            row.update(EDD=portfolio['EDD'], MDD=portfolio['MDD'], ATC=portfolio['ATC_k1'],
                       best_of_3_rules=min(portfolio['EDD'], portfolio['MDD'], portfolio['ATC_k1']),
                       best_of_9_rules=min(portfolio.values()), best_of_9_rules_seconds=sum(seconds.values()))
            for label, samples in ROLLOUTS.items():
                plan, spent = timed(lambda: best_of_rollouts(policy, case.data, mode=mode, samples=samples, seed=0))
                row[f'policy_{label}'] = checked_tardiness(plan, case.data, mode)
                row[f'policy_{label}_seconds'] = spent
            for name in meta_methods:
                row[name] = float(meta[case.case_id, mode][name])
                row[f'{name}_best'] = int(meta[case.case_id, mode][f'{name}_best'])
                row[f'{name}_seconds'] = float(meta[case.case_id, mode][f'{name}_seconds'])
            proven = None
            for setting in ('cp_sat_1s', 'cp_sat_60s'):
                ref = cpsat.get((case.case_id, mode, setting))
                if ref is not None:
                    row[setting] = int(ref['total_tardiness'])
                    row[f'{setting}_status'] = ref['solver_status']
                    row[f'{setting}_seconds'] = float(ref['wall_time'])
                    if ref['solver_status'] == 'OPTIMAL':
                        proven = int(ref['total_tardiness'])
            candidates = [row[c] for c in ('best_of_9_rules', 'policy_r9', 'cp_sat_1s', 'cp_sat_60s') if c in row]
            candidates += [row[f'{name}_best'] for name in meta_methods]
            row['best_known'] = min(candidates)
            row['best_known_proven_optimal'] = proven is not None and proven == row['best_known']
            if proven is not None and row['best_known'] < proven:
                raise ValueError(f'{case.case_id}/{mode}: a method beats a proven optimum')
            rows.append(row)
    methods = ['EDD', 'MDD', 'ATC', 'best_of_3_rules', 'best_of_9_rules', *(f'policy_{k}' for k in ROLLOUTS),
               *meta_methods, 'cp_sat_1s', 'cp_sat_60s']
    groups = {'all': rows}
    for key in sorted({(r['group'], r['num_tasks'], r['num_machines']) for r in rows}):
        groups[f'{key[0]}/n{key[1]}-m{key[2]}'] = [r for r in rows if (r['group'], r['num_tasks'], r['num_machines']) == key]
    summary = {}
    top_iga = max((m for m in meta_methods if m.startswith('IGA_')), key=lambda m: int(m.split('_')[1]))
    for name, selected in groups.items():
        present = [m for m in methods if all(m in r for r in selected)]
        tests = [paired(selected, 'policy_r1', 'MDD'), paired(selected, 'policy_r9', 'best_of_9_rules')]
        tests += [paired(selected, m, 'policy_r9') for m in meta_methods if m.startswith('IGA_')]
        tests += [paired(selected, m, n) for m, n in (('IGA_10000', 'GA_10000'), ('IGA_10000', 'SA_10000'))
                  if m in present and n in present]
        if 'cp_sat_60s' in present:
            tests += [paired(selected, top_iga, 'cp_sat_60s'), paired(selected, 'policy_r9', 'cp_sat_60s')]
        summary[name] = {
            'instances': len(selected),
            'mean': {m: statistics.fmean(r[m] for r in selected) for m in present},
            'mean_gap_to_best_known': {m: statistics.fmean(r[m] - r['best_known'] for r in selected) for m in present},
            'best_known_hits': {m: sum(r[m] == r['best_known'] for r in selected) for m in present},
            'mean_seconds': {m: statistics.fmean(r[f'{m}_seconds'] for r in selected)
                             for m in present if all(f'{m}_seconds' in r for r in selected)},
            'paired': tests}
    by_pair = {}
    for row in rows:
        by_pair.setdefault(row['case_id'], {})[row['mode']] = row
    joint_gain = {}
    for name in ('primary/n8', 'primary/n24', 'sensitivity/n8'):
        group, n = name.split('/')
        chosen = [p for p in by_pair.values() if p['fixed']['group'] == group and p['fixed']['num_tasks'] == int(n[1:])]
        gains = [(p['fixed']['best_known'] - p['joint']['best_known']) / p['fixed']['best_known']
                 for p in chosen if p['fixed']['best_known'] > 0]
        joint_gain[name] = {'pairs': len(chosen), 'fixed_positive': len(gains),
                            'mean_relative_reduction': statistics.fmean(gains) if gains else None,
                            'joint_better': sum(p['joint']['best_known'] < p['fixed']['best_known'] for p in chosen),
                            'joint_worse': sum(p['joint']['best_known'] > p['fixed']['best_known'] for p in chosen)}
    write_csv(args.output_dir / 'rows.csv', rows)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g4_comparison', 'final_policy': final,
        'inputs_sha256': {str(p): sha256(p) for p in (args.cpsat / 'rows.csv', args.policy / 'manifest.json',
                                                      args.meta / 'rows.csv')},
        'summary': summary, 'joint_gain_on_best_known': joint_gain, **provenance(__file__)})
    LOGGER.info('means: %s', json.dumps(summary['all']['mean']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
