"""Graduation: Gantt examples of fixed vs joint maintenance on representative G4 cases.

Selection rule (fixed before plotting): for each (n, m, profile) below, among
the G4 cases whose fixed-mode IGA value in the re-timed search run is
positive, take the case whose relative joint-vs-fixed reduction is the median
(lower median), i.e. a typical case rather than the best one. Both plans come
from IGA with a deterministic budget of 50 000 decodes (seed 0) and pass the
checker before they are drawn. Writes <case>.png/.pdf and manifest.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from _common import ROOT, checked_tardiness, parse_args, provenance, sha256, write_json

from fjsp_lab.maintenance.gantt import plot_fixed_vs_joint
from fjsp_lab.maintenance.generator import g4_cases
from fjsp_lab.maintenance.metaheuristics import solve_metaheuristic

LOGGER = logging.getLogger(__name__)
EXAMPLES = ((20, 2, 'mixed'), (20, 4, 'uniform2'), (50, 4, 'mixed'))
SEARCH = ROOT / 'experiments/results/g4_search_curves_retimed/rows.jsonl'
EVALUATIONS = 50000


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g10_gantt_examples')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)
    with open(SEARCH, encoding='utf-8') as handle:
        iga = {(r['case_id'], r['mode']): r['IGA']['value'] for r in map(json.loads, handle)}
    cases = {case.case_id: case for case in g4_cases()}
    chosen = []
    for n, m, profile in EXAMPLES:
        pool = sorted(((iga[cid, 'fixed'] - iga[cid, 'joint']) / iga[cid, 'fixed'], cid)
                      for cid, case in cases.items()
                      if (case.num_tasks, case.num_machines, case.profile) == (n, m, profile) and iga[cid, 'fixed'] > 0)
        reduction, case_id = pool[(len(pool) - 1) // 2]
        case = cases[case_id]
        plans = {mode: solve_metaheuristic(case.data, mode=mode, algorithm='IGA', evaluations=EVALUATIONS,
                                           seed=0).result for mode in ('fixed', 'joint')}
        values = {mode: checked_tardiness(plan, case.data, mode) for mode, plan in plans.items()}
        title = (f'{case_id}: n={n}, m={m}, windows per machine '
                 f'{[len(w) for w in case.data.windows]}, alpha={case.alpha_percent}%, beta={case.beta_percent}%')
        for suffix in ('png', 'pdf'):
            plot_fixed_vs_joint(case.data, plans['fixed'], plans['joint'], args.output_dir / f'{case_id}.{suffix}',
                                title=title)
        chosen.append({'case_id': case_id, 'candidates': len(pool), 'median_reduction_in_search_run': reduction,
                       'fixed_tardiness': values['fixed'], 'joint_tardiness': values['joint']})
        LOGGER.info('%s: fixed %d, joint %d', case_id, values['fixed'], values['joint'])
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g10_gantt_examples', 'examples': chosen, 'evaluations': EVALUATIONS,
        'search_rows_sha256': sha256(SEARCH), **prov})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
