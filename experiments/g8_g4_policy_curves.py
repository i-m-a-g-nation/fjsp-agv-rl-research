"""Graduation G4: anytime points of the trained attention policy on the 576 G4 test instances.

Runs in the PyTorch environment. Loads the validation-selected checkpoint of
a g6_attention_policy run (hash-checked). Per instance, timed one instance at
a time: a greedy episode, then K = 4, 16, 64 sampled episodes in one batch
(seed = instance index). Timing includes feature computation, environment
steps and the decoder's final check. The main timing is on ``--device``
(GPU); greedy and K = 4 are timed again on the CPU for reference. Every plan
is checked inside the environment. Writes rows.jsonl and manifest.json.

G5 options: ``--grid`` (default ``g4``), ``--checkpoint`` (``best`` or
``best_bc``, the imitation-only model) and ``--save-sequences``, which runs
greedy + 16 samples once more (timed as one pipeline) and writes the distinct
decoder sequences to sequences.jsonl for the warm-started IGA (g11).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time

from _common import parse_args, provenance, sha256, write_json

import torch

from fjsp_lab.maintenance.attention_policy import load, rollout
from fjsp_lab.maintenance.generator import GRIDS, grid_cases

LOGGER = logging.getLogger(__name__)
SAMPLES = (4, 16, 64)
CPU_SAMPLES = (4,)
WARM_SAMPLES = 16
WARM_LIMIT = 40                               # IGA population size


def warm_start(model, problem, device, index) -> dict:
    """Greedy + WARM_SAMPLES samples timed together; the distinct sequences, best first (at most WARM_LIMIT)."""
    started = time.perf_counter()
    greedy, greedy_seq = rollout(model, [problem], samples=1, greedy=True, device=device, sequences=True)
    generator = torch.Generator().manual_seed(index)
    sampled, sampled_seq = rollout(model, [problem], samples=WARM_SAMPLES, greedy=False, generator=generator,
                                   device=device, sequences=True)
    if device.startswith('cuda'):
        torch.cuda.synchronize()
    seconds = time.perf_counter() - started
    pairs = sorted(zip(greedy[0] + sampled[0], greedy_seq[0] + sampled_seq[0]), key=lambda pair: pair[0])
    distinct, seen = [], set()
    for value, sequence in pairs:
        if tuple(sequence) not in seen:
            seen.add(tuple(sequence))
            distinct.append({'value': value, 'sequence': sequence})
    return {'seconds': seconds, 'best': pairs[0][0], 'sequences': distinct[:WARM_LIMIT]}


def timed_points(model, problem, device, samples, index) -> dict:
    out = {}
    started = time.perf_counter()
    greedy, _ = rollout(model, [problem], samples=1, greedy=True, device=device)
    out['greedy'] = {'value': greedy[0][0], 'seconds': time.perf_counter() - started}
    for k in samples:
        generator = torch.Generator().manual_seed(index)
        started = time.perf_counter()
        sampled, _ = rollout(model, [problem], samples=k, greedy=False, generator=generator, device=device)
        out[f'sample{k}'] = {'value': min(sampled[0]), 'seconds': time.perf_counter() - started}
    if device.startswith('cuda'):
        torch.cuda.synchronize()
    return out


def main() -> int:
    def extra(parser):
        parser.add_argument('--policy-dir', type=Path, required=True)
        parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--grid', choices=tuple(GRIDS), default='g4')
        parser.add_argument('--checkpoint', choices=('best', 'best_bc'), default='best')
        parser.add_argument('--save-sequences', action='store_true')

    args = parse_args(__doc__.splitlines()[0], 'g8_g4_policy_curves', extra)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__, packages=('numpy', 'torch'))
    summary = json.loads((args.policy_dir / 'summary.json').read_text(encoding='utf-8'))
    chosen = summary[args.checkpoint]
    path = args.policy_dir / f'{args.checkpoint}.pt'
    model = load(path, expected_sha256=chosen['sha256'], device=args.device)
    cpu_model = load(path, expected_sha256=chosen['sha256'], device='cpu')
    torch.set_num_threads(1)                   # single-core CPU timing, like the metaheuristics
    cases = grid_cases(args.grid)[:args.limit]
    warm = (cases[0].data, 'joint')
    timed_points(model, warm, args.device, SAMPLES, 0)
    timed_points(cpu_model, warm, 'cpu', CPU_SAMPLES, 0)
    if args.save_sequences:
        warm_start(model, warm, args.device, 0)
    started = time.monotonic()
    warm_out = open(args.output_dir / 'sequences.jsonl', 'w', encoding='utf-8', newline='\n') if args.save_sequences else None
    with open(args.output_dir / 'rows.jsonl', 'w', encoding='utf-8', newline='\n') as out:
        index = 0
        for case in cases:
            for mode in ('fixed', 'joint'):
                problem = (case.data, mode)
                row = {'case_id': case.case_id, 'mode': mode, 'num_tasks': case.num_tasks,
                       'num_machines': case.num_machines,
                       'device': timed_points(model, problem, args.device, SAMPLES, index),
                       'cpu': timed_points(cpu_model, problem, 'cpu', CPU_SAMPLES, index)}
                out.write(json.dumps(row, separators=(',', ':')) + '\n')
                if warm_out is not None:
                    entry = {'case_id': case.case_id, 'mode': mode, **warm_start(model, problem, args.device, index)}
                    warm_out.write(json.dumps(entry, separators=(',', ':')) + '\n')
                index += 1
            if index % 48 == 0:
                LOGGER.info('%d instances (%.1f min)', index, (time.monotonic() - started) / 60)
    if warm_out is not None:
        warm_out.close()
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g8_g4_policy_curves', 'policy_dir': str(args.policy_dir), 'grid': args.grid,
        'checkpoint_name': args.checkpoint, 'checkpoint': chosen,
        'warm_start': {'samples': WARM_SAMPLES, 'limit': WARM_LIMIT} if args.save_sequences else None,
        'policy_summary_sha256': sha256(args.policy_dir / 'summary.json'), 'samples': SAMPLES,
        'cpu_samples': CPU_SAMPLES, 'device': args.device,
        'gpu': torch.cuda.get_device_name(0) if args.device.startswith('cuda') else None, 'limit': args.limit,
        'elapsed_minutes': round((time.monotonic() - started) / 60, 1), **prov})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
