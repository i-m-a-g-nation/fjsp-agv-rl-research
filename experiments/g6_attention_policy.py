"""Graduation: train the attention policy, behaviour cloning on IGA teachers then REINFORCE.

Runs in the PyTorch environment (see START_HERE.md). Reads a g5_teacher_data
run; never touches a test split. Checkpoint selection uses the validation
mean greedy tardiness only. Writes best.pt and summary.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import random
import statistics
import time

from _common import parse_args, provenance, sha256, write_json

import torch

from fjsp_lab.maintenance.attention_policy import (
    AttentionPolicy, PolicyConfig, imitation_loss, reinforce_loss, rollout, save,
)
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance

LOGGER = logging.getLogger(__name__)


def add_args(parser) -> None:
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--train-limit', type=int, default=None)
    parser.add_argument('--bc-epochs', type=int, default=8)
    parser.add_argument('--bc-batch', type=int, default=64)
    parser.add_argument('--bc-lr', type=float, default=1e-3)
    parser.add_argument('--rl-steps', type=int, default=1000)
    parser.add_argument('--rl-batch', type=int, default=32)
    parser.add_argument('--rl-samples', type=int, default=16)
    parser.add_argument('--rl-lr', type=float, default=1e-4)
    parser.add_argument('--eval-every', type=int, default=10)
    parser.add_argument('--max-minutes', type=float, default=120.0)


def read_rows(path: Path, limit: int | None = None) -> list[dict]:
    rows = []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            row['problem'] = (ParallelMaintenanceInstance.from_record(row['instance']), row['mode'])
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def greedy_mean(model, rows, *, device, batch=100) -> float:
    model.eval()
    values = []
    for start in range(0, len(rows), batch):
        greedy, _ = rollout(model, [r['problem'] for r in rows[start:start + batch]], samples=1, greedy=True,
                            device=device)
        values += [g[0] for g in greedy]
    return statistics.fmean(values)


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g6_attention_policy', add_args)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    train_rows = read_rows(args.data_dir / 'train.jsonl', args.train_limit)
    val_rows = read_rows(args.data_dir / 'validation.jsonl')
    reference = {'teacher': statistics.fmean(r['teacher_tardiness'] for r in val_rows),
                 'MDD': statistics.fmean(r['mdd_tardiness'] for r in val_rows)}
    LOGGER.info('train %d, validation %d, reference %s', len(train_rows), len(val_rows), reference)
    model = AttentionPolicy(PolicyConfig()).to(args.device)
    history, best = [], {'val_greedy': float('inf')}
    started = time.monotonic()

    def checkpoint(stage, step):
        value = greedy_mean(model, val_rows, device=args.device)
        history.append({'stage': stage, 'step': step, 'val_greedy': value,
                        'minutes': round((time.monotonic() - started) / 60, 2)})
        LOGGER.info('%s %d: val greedy %.3f (%.1f min)', stage, step, value, history[-1]['minutes'])
        if value < best['val_greedy']:
            best.update(val_greedy=value, stage=stage, step=step, sha256=save(model, args.output_dir / 'best.pt'))
        model.train()

    def update(optimizer, loss):
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

    optimizer = torch.optim.Adam(model.parameters(), lr=args.bc_lr)
    for epoch in range(args.bc_epochs):
        order = list(range(len(train_rows)))
        rng.shuffle(order)
        model.train()
        for start in range(0, len(order), args.bc_batch):
            chunk = [train_rows[k] for k in order[start:start + args.bc_batch]]
            update(optimizer, imitation_loss(model, [r['problem'] for r in chunk],
                                             [r['teacher_actions'] for r in chunk], device=args.device))
        checkpoint('bc', epoch + 1)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.rl_lr)
    generator = torch.Generator().manual_seed(args.seed)
    for step in range(1, args.rl_steps + 1):
        if time.monotonic() - started > args.max_minutes * 60:
            LOGGER.info('time budget reached at RL step %d', step)
            break
        chunk = rng.sample(train_rows, args.rl_batch)
        model.train()
        loss, _ = reinforce_loss(model, [r['problem'] for r in chunk], samples=args.rl_samples, generator=generator,
                                 device=args.device, scale=[r['teacher_tardiness'] + 1.0 for r in chunk])
        update(optimizer, loss)
        if step % args.eval_every == 0:
            checkpoint('rl', step)

    write_json(args.output_dir / 'summary.json', {
        'experiment': 'g6_attention_policy',
        'arguments': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        'reference_validation': reference, 'best': best, 'history': history,
        'elapsed_minutes': round((time.monotonic() - started) / 60, 2), 'torch': torch.__version__,
        'cuda': torch.version.cuda, 'data_manifest_sha256': sha256(args.data_dir / 'manifest.json'),
        **provenance(__file__, packages=('numpy', 'torch'))})
    LOGGER.info('best %s', json.dumps(best))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
