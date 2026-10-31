"""Graduation G4: anytime points of the trained attention policy on the 576 G4 test instances.

Runs in the PyTorch environment. Loads the validation-selected checkpoint of
a g6_attention_policy run (hash-checked). Per instance, timed one instance at
a time: a greedy episode, then K = 4, 16, 64 sampled episodes in one batch
(seed = instance index). Timing includes feature computation, environment
steps and the decoder's final check. The main timing is on ``--device``
(GPU); greedy and K = 4 are timed again on the CPU for reference. Every plan
is checked inside the environment. Writes rows.jsonl and manifest.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time

from _common import parse_args, provenance, sha256, write_json

import torch

from fjsp_lab.maintenance.attention_policy import load, rollout
from fjsp_lab.maintenance.generator import g4_cases

LOGGER = logging.getLogger(__name__)
SAMPLES = (4, 16, 64)
CPU_SAMPLES = (4,)


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

    args = parse_args(__doc__.splitlines()[0], 'g8_g4_policy_curves', extra)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__, packages=('numpy', 'torch'))
    summary = json.loads((args.policy_dir / 'summary.json').read_text(encoding='utf-8'))
    model = load(args.policy_dir / 'best.pt', expected_sha256=summary['best']['sha256'], device=args.device)
    cpu_model = load(args.policy_dir / 'best.pt', expected_sha256=summary['best']['sha256'], device='cpu')
    torch.set_num_threads(1)                   # single-core CPU timing, like the metaheuristics
    cases = g4_cases()[:args.limit]
    warm = (cases[0].data, 'joint')
    timed_points(model, warm, args.device, SAMPLES, 0)
    timed_points(cpu_model, warm, 'cpu', CPU_SAMPLES, 0)
    started = time.monotonic()
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
                index += 1
            if index % 48 == 0:
                LOGGER.info('%d instances (%.1f min)', index, (time.monotonic() - started) / 60)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g8_g4_policy_curves', 'policy_dir': str(args.policy_dir), 'checkpoint': summary['best'],
        'policy_summary_sha256': sha256(args.policy_dir / 'summary.json'), 'samples': SAMPLES,
        'cpu_samples': CPU_SAMPLES, 'device': args.device,
        'gpu': torch.cuda.get_device_name(0) if args.device.startswith('cuda') else None, 'limit': args.limit,
        'elapsed_minutes': round((time.monotonic() - started) / 60, 1), **prov})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
