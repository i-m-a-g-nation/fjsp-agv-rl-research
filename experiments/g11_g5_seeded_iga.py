"""Graduation G5 (E3): IGA warm-started with the attention policy's sequences.

Input: a g8_g4_policy_curves run made with ``--save-sequences`` (per instance:
the time of greedy + 16 samples and up to 40 distinct decoder sequences, best
first). Per instance, IGA (seed 0, default settings) starts from those
sequences, the rest of the population as usual, and runs until the pipeline
has used ``TOTAL_SECONDS``: its time limit is the total minus the policy's
time. The trace is shifted by the policy's time, so a point (t, decodes, T)
means "best T after t seconds of policy + IGA"; its first point is the
policy's best at the policy's time. Every plan is re-checked and IGA must not
end worse than the best seed. One JSON line per instance in rows.jsonl
(``--resume`` skips finished ones); docs/protocols/g5_supplement_protocol.md.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import logging
from pathlib import Path
import time

from _common import checked_tardiness, parse_args, provenance, sha256, write_json

from fjsp_lab.maintenance.generator import GRIDS, grid_cases
from fjsp_lab.maintenance.metaheuristics import solve_metaheuristic

LOGGER = logging.getLogger(__name__)
TOTAL_SECONDS = 10.0
MIN_SEARCH_SECONDS = 0.01        # below this the policy's result is final
SEED = 0
PROCESSES = 2


def run_instance(job) -> dict:
    case, mode, warm = job
    data, rl_seconds = case.data, warm['seconds']
    seeds = [item['sequence'] for item in warm['sequences']]
    row = {'case_id': case.case_id, 'mode': mode, 'num_tasks': case.num_tasks, 'num_machines': case.num_machines,
           'rl_seconds': rl_seconds, 'rl_best': warm['best'], 'seeds': len(seeds)}
    trace = [[rl_seconds, 0, warm['best']]]
    value, decodes = warm['best'], 0
    remaining = TOTAL_SECONDS - rl_seconds
    if remaining >= MIN_SEARCH_SECONDS:
        outcome = solve_metaheuristic(data, mode=mode, algorithm='IGA', evaluations=10**9, seed=SEED,
                                      initial_sequences=seeds, time_limit=remaining)
        value, decodes = checked_tardiness(outcome.result, data, mode), outcome.evaluations
        if value > warm['best']:
            raise ValueError(f'{case.case_id}/{mode}: warm-started IGA ended worse than its best seed')
        trace += [[rl_seconds + seconds, count, best] for seconds, count, best in outcome.trace if best < warm['best']]
    row['RL+IGA'] = {'value': value, 'decodes': decodes, 'trace': trace}
    return row


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g11_g5_seeded_iga', resumable=True,
                      extra=lambda p: (p.add_argument('--policy', type=Path, required=True,
                                                      help='g8 run made with --save-sequences'),
                                       p.add_argument('--grid', choices=tuple(GRIDS), required=True),
                                       p.add_argument('--limit', type=int, default=None),
                                       p.add_argument('--processes', type=int, default=PROCESSES)))
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)   # recorded at start: the code that actually runs
    with open(args.policy / 'sequences.jsonl', encoding='utf-8') as handle:
        warm = {(row['case_id'], row['mode']): row for row in map(json.loads, handle)}
    path = args.output_dir / 'rows.jsonl'
    done = set()
    if path.exists():
        with open(path, encoding='utf-8') as handle:
            done = {(row['case_id'], row['mode']) for row in map(json.loads, handle)}
    jobs = [(case, mode, warm[case.case_id, mode]) for case in grid_cases(args.grid)[:args.limit]
            for mode in ('fixed', 'joint') if (case.case_id, mode) not in done]
    LOGGER.info('%d instances to run (%d already done)', len(jobs), len(done))
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.processes) as pool, open(path, 'a', encoding='utf-8', newline='\n') as out:
        futures = [pool.submit(run_instance, job) for job in jobs]
        for count, future in enumerate(as_completed(futures), 1):
            out.write(json.dumps(future.result(), separators=(',', ':')) + '\n')
            out.flush()
            if count % 24 == 0:
                LOGGER.info('%d/%d (%.0f min)', count, len(jobs), (time.monotonic() - started) / 60)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g11_g5_seeded_iga', 'grid': args.grid, 'limit': args.limit, 'total_seconds': TOTAL_SECONDS,
        'seed': SEED, 'parallel_processes': args.processes, 'instances': len(done) + len(jobs),
        'policy_run': str(args.policy), 'sequences_sha256': sha256(args.policy / 'sequences.jsonl'),
        'elapsed_minutes_this_session': round((time.monotonic() - started) / 60, 1), **prov})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
