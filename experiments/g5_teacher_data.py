"""Graduation: IGA teacher trajectories for the attention policy (project environment).

Writes JSON-lines files that the PyTorch environment reads without the generator:
* train.jsonl: the ``teacher_train`` split (20 000 instances, seeds disjoint
  from every other split) with an IGA-10k plan replayed into environment actions;
* validation.jsonl: the validation split with IGA and MDD reference values.
The test split is never written here.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import logging
import time

from _common import checked_tardiness, parse_args, provenance, sha256, write_json

from fjsp_lab.maintenance.env import actions_for_plan
from fjsp_lab.maintenance.generator import split_instances
from fjsp_lab.maintenance.metaheuristics import solve_metaheuristic
from fjsp_lab.maintenance.rules import solve_dispatch_rule

LOGGER = logging.getLogger(__name__)
TEACHER = {'algorithm': 'IGA', 'evaluations': 10000, 'seed': 0}
PROCESSES = 8


def label(job) -> dict:
    instance, split = job
    outcome = solve_metaheuristic(instance.data, mode=instance.mode, **TEACHER)
    row = {'split': split, 'seed': instance.seed, 'mode': instance.mode, 'num_tasks': instance.num_tasks,
           'num_machines': instance.num_machines, 'instance': instance.data.to_record(),
           'teacher_tardiness': checked_tardiness(outcome.result, instance.data, instance.mode),
           'mdd_tardiness': solve_dispatch_rule(instance.data, mode=instance.mode, rule='MDD').total_tardiness}
    if split == 'train':
        row['teacher_actions'] = actions_for_plan(outcome.result, instance.data, instance.mode)
    return row


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g5_teacher_data',
                      lambda p: p.add_argument('--limit', type=int, default=None, help='first N per split (smoke only)'))
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    started, counts = time.monotonic(), {}
    for split, name in (('train', 'teacher_train'), ('validation', 'validation')):
        instances = split_instances(name)[:args.limit]
        with ProcessPoolExecutor(max_workers=PROCESSES) as pool:
            rows = list(pool.map(label, [(i, split) for i in instances], chunksize=16))
        with open(args.output_dir / f'{split}.jsonl', 'w', encoding='utf-8', newline='\n') as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
        counts[split] = len(rows)
        LOGGER.info('%s: %d instances', split, len(rows))
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g5_teacher_data', 'teacher': TEACHER, 'counts': counts, 'limit': args.limit,
        'file_sha256': {f'{s}.jsonl': sha256(args.output_dir / f'{s}.jsonl') for s in counts},
        'elapsed_seconds': round(time.monotonic() - started, 1), **provenance(__file__)})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
