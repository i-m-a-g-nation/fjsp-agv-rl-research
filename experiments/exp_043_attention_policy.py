"""Train the attention policy: behaviour cloning on IGA teachers, then REINFORCE.

Runs in an environment with PyTorch (see START_HERE). Reads the exp_042
JSON-lines data; never touches a test split. Checkpoint selection uses the
validation mean greedy tardiness only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch

from src.graduation.attention_policy import (
    AttentionPolicy, PolicyConfig, imitation_loss, reinforce_loss, rollout, save,
)
from src.graduation.teacher_data import record_to_instance

LOGGER = logging.getLogger(__name__)
SOURCES = ('src/graduation/attention_policy.py', 'src/graduation/action_features.py',
           'src/graduation/teacher_data.py', 'experiments/exp_043_attention_policy.py')


def read_rows(path: Path, limit: int | None = None) -> list[dict]:
    rows = []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            row['problem'] = (record_to_instance(row['instance']), row['mode'])
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def evaluate(model, rows, *, device, samples=1, batch=100, seed=0) -> float:
    model.eval()
    values = []
    generator = torch.Generator().manual_seed(seed)
    for start in range(0, len(rows), batch):
        problems = [r['problem'] for r in rows[start:start + batch]]
        greedy, _ = rollout(model, problems, samples=1, greedy=True, device=device)
        best = [g[0] for g in greedy]
        if samples > 1:
            sampled, _ = rollout(model, problems, samples=samples - 1, greedy=False,
                                 generator=generator, device=device)
            best = [min(b, *s) for b, s in zip(best, sampled)]
        values += best
    return statistics.fmean(values)


def train(args) -> dict:
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    device = args.device
    train_rows = read_rows(Path(args.data_dir) / 'train.jsonl', args.train_limit)
    val_rows = read_rows(Path(args.data_dir) / 'validation.jsonl')
    reference = {'teacher': statistics.fmean(r['teacher_tardiness'] for r in val_rows),
                 'MDD': statistics.fmean(r['mdd_tardiness'] for r in val_rows)}
    LOGGER.info('train %d, validation %d, reference %s', len(train_rows), len(val_rows), reference)
    model = AttentionPolicy(PolicyConfig()).to(device)
    history, best = [], {'val_greedy': float('inf')}
    started = time.monotonic()

    def checkpoint(stage, step):
        value = evaluate(model, val_rows, device=device)
        history.append({'stage': stage, 'step': step, 'val_greedy': value,
                        'minutes': round((time.monotonic() - started) / 60, 2)})
        LOGGER.info('%s %d: val greedy %.3f (%.1f min)', stage, step, value, history[-1]['minutes'])
        if value < best['val_greedy']:
            best.update(val_greedy=value, stage=stage, step=step,
                        sha256=save(model, output / 'best.pt'))
        model.train()

    optimizer = torch.optim.Adam(model.parameters(), lr=args.bc_lr)
    for epoch in range(args.bc_epochs):
        order = list(range(len(train_rows)))
        rng.shuffle(order)
        model.train()
        for start in range(0, len(order), args.bc_batch):
            chunk = [train_rows[k] for k in order[start:start + args.bc_batch]]
            loss = imitation_loss(model, [r['problem'] for r in chunk], [r['teacher_actions'] for r in chunk],
                                  device=device)
            optimizer.zero_grad()
            loss.backward()
            nn_utils_clip(model)
            optimizer.step()
        checkpoint('bc', epoch + 1)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.rl_lr)
    generator = torch.Generator().manual_seed(args.seed)
    for step in range(1, args.rl_steps + 1):
        if time.monotonic() - started > args.max_minutes * 60:
            LOGGER.info('time budget reached at RL step %d', step)
            break
        chunk = rng.sample(train_rows, args.rl_batch)
        model.train()
        loss, _ = reinforce_loss(model, [r['problem'] for r in chunk], samples=args.rl_samples,
                                 generator=generator, device=device,
                                 scale=[r['teacher_tardiness'] + 1.0 for r in chunk])
        optimizer.zero_grad()
        loss.backward()
        nn_utils_clip(model)
        optimizer.step()
        if step % args.eval_every == 0:
            checkpoint('rl', step)

    summary = {
        'experiment': 'exp_043_attention_policy',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'arguments': vars(args), 'reference_validation': reference, 'best': best, 'history': history,
        'elapsed_minutes': round((time.monotonic() - started) / 60, 2),
        'environment': {'python': platform.python_version(), 'torch': torch.__version__,
                        'cuda': torch.version.cuda, 'device': device,
                        'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                                     text=True, check=False).stdout.strip()},
        'data_manifest_sha256': hashlib.sha256((Path(args.data_dir) / 'manifest.json').read_bytes()).hexdigest(),
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return summary


def nn_utils_clip(model) -> None:
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--train-limit', type=int, default=None)
    parser.add_argument('--bc-epochs', type=int, default=3)
    parser.add_argument('--bc-batch', type=int, default=64)
    parser.add_argument('--bc-lr', type=float, default=1e-3)
    parser.add_argument('--rl-steps', type=int, default=1000)
    parser.add_argument('--rl-batch', type=int, default=32)
    parser.add_argument('--rl-samples', type=int, default=16)
    parser.add_argument('--rl-lr', type=float, default=1e-4)
    parser.add_argument('--eval-every', type=int, default=50)
    parser.add_argument('--max-minutes', type=float, default=120.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    summary = train(args)
    LOGGER.info('best %s', json.dumps(summary['best']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
