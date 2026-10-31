"""Graduation: IGA teacher trajectories for the attention policy (project environment).

Writes JSON-lines files that the PyTorch environment reads without the generator:
* train.jsonl: training instances with an IGA plan converted to episode actions;
* validation.jsonl: validation instances with IGA and MDD reference values.
Test instances are never written here.

``--set g3a``: single-window G3A splits (teacher_train / validation), IGA 10 000
decodes, actions of the job x machine MDP (``kind = 'action'``).
``--set g4``: periodic-maintenance G4 splits, IGA 5 000 decodes, actions of the
decoder MDP (``kind = 'sequence'``); see docs/protocols/g4_periodic_protocol.md.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import logging
import time

from _common import checked_tardiness, parse_args, provenance, sha256, write_json

from fjsp_lab.maintenance.env import actions_for_plan
from fjsp_lab.maintenance.generator import g4_split, split_instances
from fjsp_lab.maintenance.metaheuristics import solve_metaheuristic
from fjsp_lab.maintenance.rules import solve_dispatch_rule
from fjsp_lab.maintenance.sequence_env import teacher_actions

LOGGER = logging.getLogger(__name__)
SETS = {
    'g3a': {'kind': 'action', 'teacher': {'algorithm': 'IGA', 'evaluations': 10000, 'seed': 0},
            'splits': {'train': lambda: split_instances('teacher_train'), 'validation': lambda: split_instances('validation')}},
    'g4': {'kind': 'sequence', 'teacher': {'algorithm': 'IGA', 'evaluations': 5000, 'seed': 0},
           'splits': {'train': lambda: g4_split('train'), 'validation': lambda: g4_split('validation')}},
}
PROCESSES = 8


def label(job) -> dict:
    instance, split, name = job
    spec = SETS[name]
    outcome = solve_metaheuristic(instance.data, mode=instance.mode, **spec['teacher'])
    row = {'split': split, 'seed': instance.seed, 'mode': instance.mode, 'num_tasks': instance.num_tasks,
           'num_machines': instance.num_machines, 'instance': instance.data.to_record(),
           'teacher_tardiness': checked_tardiness(outcome.result, instance.data, instance.mode),
           'mdd_tardiness': solve_dispatch_rule(instance.data, mode=instance.mode, rule='MDD').total_tardiness}
    if split == 'train':
        row['teacher_actions'] = (actions_for_plan(outcome.result, instance.data, instance.mode)
                                  if spec['kind'] == 'action'
                                  else teacher_actions(list(outcome.sequence), instance.data, instance.mode))
    return row


def main() -> int:
    def extra(parser):
        parser.add_argument('--set', choices=sorted(SETS), default='g3a')
        parser.add_argument('--limit', type=int, default=None, help='first N per split (smoke only)')

    args = parse_args(__doc__.splitlines()[0], 'g5_teacher_data', extra)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)   # recorded at start: the code that actually runs
    spec, started, counts = SETS[args.set], time.monotonic(), {}
    for split, make in spec['splits'].items():
        instances = make()[:args.limit]
        with ProcessPoolExecutor(max_workers=PROCESSES) as pool:
            rows = list(pool.map(label, [(i, split, args.set) for i in instances], chunksize=8))
        with open(args.output_dir / f'{split}.jsonl', 'w', encoding='utf-8', newline='\n') as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
        counts[split] = len(rows)
        LOGGER.info('%s: %d instances (%.0f s)', split, len(rows), time.monotonic() - started)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g5_teacher_data', 'set': args.set, 'kind': spec['kind'], 'teacher': spec['teacher'],
        'counts': counts, 'limit': args.limit,
        'file_sha256': {f'{s}.jsonl': sha256(args.output_dir / f'{s}.jsonl') for s in counts},
        'elapsed_seconds': round(time.monotonic() - started, 1), **prov})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
