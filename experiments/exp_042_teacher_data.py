"""Teacher data for the attention policy (runs in the project environment).

Writes JSON-lines files that the PyTorch environment can read without the
instance generator:
* train: generated instances (seeds disjoint from every earlier split) with
  an IGA teacher plan replayed into environment actions;
* validation: the exp_036 validation split with IGA and MDD reference values.
Test splits are never written here.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graduation.dispatch_rules import solve_dispatch_rule
from src.graduation.metaheuristics import solve_metaheuristic
from src.graduation.scoring_training import make_instances
from src.graduation.teacher_data import instance_to_record, plan_to_actions

LOGGER = logging.getLogger(__name__)
PROTOCOL = {
    'train': {'seeds': [100000, 120000], 'sampler_seed': 11, 'balanced': False},
    'validation': {'seeds': [20000, 20200], 'sampler_seed': 2, 'balanced': False},
    'teacher': {'algorithm': 'IGA', 'evaluations': 10000, 'seed': 0},
    'parallel_processes': 8,
}
SOURCES = ('src/graduation/teacher_data.py', 'src/graduation/metaheuristics.py',
           'experiments/exp_042_teacher_data.py')


def _label(job: tuple) -> dict:
    instance, teacher, split = job
    outcome = solve_metaheuristic(instance.data, mode=instance.mode, algorithm=teacher['algorithm'],
                                  evaluations=teacher['evaluations'], seed=teacher['seed'])
    row = {'split': split, 'seed': instance.seed, 'mode': instance.mode, 'num_tasks': instance.num_tasks,
           'num_machines': instance.num_machines, 'instance': instance_to_record(instance.data),
           'teacher_tardiness': outcome.result.total_tardiness,
           'mdd_tardiness': solve_dispatch_rule(instance.data, mode=instance.mode, rule='MDD').total_tardiness}
    if split == 'train':
        row['teacher_actions'] = plan_to_actions(outcome.result, instance.data, instance.mode)
    return row


def run(output_dir: Path, protocol: dict = PROTOCOL, limit: int | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    counts = {}
    for split in ('train', 'validation'):
        spec = protocol[split]
        instances = make_instances(range(*spec['seeds']), sampler_seed=spec['sampler_seed'],
                                   balanced=spec['balanced'])[:limit]
        with ProcessPoolExecutor(max_workers=protocol['parallel_processes']) as pool:
            rows = list(pool.map(_label, [(i, protocol['teacher'], split) for i in instances], chunksize=16))
        with open(output_dir / f'{split}.jsonl', 'w', encoding='utf-8', newline='\n') as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
        counts[split] = len(rows)
        LOGGER.info('%s: %d instances', split, len(rows))
    manifest = {
        'experiment': 'exp_042_teacher_data',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'protocol': protocol, 'counts': counts,
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                     text=True, check=False).stdout.strip(),
        'file_sha256': {f'{s}.jsonl': hashlib.sha256((output_dir / f'{s}.jsonl').read_bytes()).hexdigest()
                        for s in counts},
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    }
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'experiments' / 'runs' / 'exp_042_teacher_data')
    parser.add_argument('--limit', type=int, default=None, help='first N instances per split (pilot only)')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    manifest = run(args.output_dir, limit=args.limit)
    LOGGER.info('done %s in %.1f s', manifest['counts'], manifest['elapsed_seconds'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
