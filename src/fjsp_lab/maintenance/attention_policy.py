"""Attention scoring policy (PyTorch) on the construction environment.

Each step featurizes every legal action with ``features.action_candidates`` (19
values), lets the candidates attend to each other with a small Transformer
encoder, and scores them; illegal actions never enter the softmax, so every
finished episode is a checker-accepted plan from the environment. Episodes run
in lockstep so one forward pass serves every active environment.

Training: behaviour cloning on teacher action sequences, then REINFORCE
with a shared per-instance baseline (mean return of the K sampled
rollouts of that instance, as in POMO). No PPO, no value network.

This module needs PyTorch; the rest of the project does not import it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
import torch
from torch import nn

from fjsp_lab.maintenance.env import ParallelMaintenanceEnv
from fjsp_lab.maintenance.features import FEATURE_COUNT, action_candidates
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance


@dataclass(frozen=True)
class PolicyConfig:
    width: int = 128
    layers: int = 3
    heads: int = 8
    feedforward: int = 256


class AttentionPolicy(nn.Module):
    def __init__(self, config: PolicyConfig = PolicyConfig()):
        super().__init__()
        self.config = config
        self.embed = nn.Linear(FEATURE_COUNT, config.width)
        layer = nn.TransformerEncoderLayer(config.width, config.heads, config.feedforward, dropout=0.0,
                                           batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, config.layers, enable_nested_tensor=False)
        self.head = nn.Sequential(nn.LayerNorm(config.width), nn.Linear(config.width, 1))

    def forward(self, features: torch.Tensor, padding: torch.Tensor) -> torch.Tensor:
        """features [E, C, F], padding [E, C] (True = no candidate) -> logits [E, C]."""
        hidden = self.encoder(self.embed(features), src_key_padding_mask=padding)
        return self.head(hidden).squeeze(-1).masked_fill(padding, float('-inf'))


def _batch(rows: list[np.ndarray], device) -> tuple[torch.Tensor, torch.Tensor]:
    width = max(len(r) for r in rows)
    features = np.zeros((len(rows), width, FEATURE_COUNT), dtype=np.float32)
    padding = np.ones((len(rows), width), dtype=bool)
    for k, r in enumerate(rows):
        features[k, :len(r)] = r
        padding[k, :len(r)] = False
    return torch.from_numpy(features).to(device), torch.from_numpy(padding).to(device)


def rollout(model: AttentionPolicy, problems: list[tuple[ParallelMaintenanceInstance, str]], *,
            samples: int, greedy: bool, generator: torch.Generator | None = None,
            device: str = 'cpu', track_gradients: bool = False) -> tuple[list[list[int]], torch.Tensor | None]:
    """Run ``samples`` episodes per problem in lockstep.

    Returns tardiness[problem][sample] and, when ``track_gradients``, the
    summed log-probability of each episode's actions as a [P*samples] tensor.
    With ``greedy`` every sample is the argmax episode.
    """
    envs = [ParallelMaintenanceEnv(data, mode=mode) for data, mode in problems for _ in range(samples)]
    remaining = [env.total_steps for env in envs]
    tardiness = [None] * len(envs)
    log_terms = [[] for _ in envs]
    with torch.set_grad_enabled(track_gradients):
        while True:
            active = [k for k, left in enumerate(remaining) if left > 0]
            if not active:
                break
            candidates = [action_candidates(envs[k]) for k in active]
            features, padding = _batch([rows for _, rows in candidates], device)
            logits = model(features, padding)
            log_probs = torch.log_softmax(logits, dim=-1)
            if greedy:
                choice = logits.argmax(dim=-1)
            else:
                probabilities = log_probs.exp().float().cpu()
                choice = torch.multinomial(probabilities, 1, generator=generator).squeeze(-1).to(device)
            if track_gradients:
                picked = log_probs.gather(1, choice.unsqueeze(1)).squeeze(1)
            choice = choice.tolist()
            for slot, k in enumerate(active):
                step = envs[k].step(candidates[slot][0][choice[slot]])
                remaining[k] -= 1
                if track_gradients:
                    log_terms[k].append(picked[slot])
                if step.terminated:
                    tardiness[k] = step.result.total_tardiness
    if any(t is None for t in tardiness):
        raise RuntimeError('An episode did not terminate')
    grouped = [tardiness[p * samples:(p + 1) * samples] for p in range(len(problems))]
    total = torch.stack([torch.stack(t).sum() for t in log_terms]) if track_gradients else None
    return grouped, total


def imitation_loss(model: AttentionPolicy, problems: list[tuple[ParallelMaintenanceInstance, str]],
                   teacher_actions: list[list[int]], device: str = 'cpu') -> torch.Tensor:
    """Mean cross-entropy of the teacher action over every step of every problem."""
    envs = [ParallelMaintenanceEnv(data, mode=mode) for data, mode in problems]
    steps = [0] * len(envs)
    losses = []
    while True:
        active = [k for k, env in enumerate(envs) if steps[k] < len(teacher_actions[k])]
        if not active:
            break
        candidates = [action_candidates(envs[k]) for k in active]
        targets = []
        for slot, k in enumerate(active):
            action = teacher_actions[k][steps[k]]
            legal = candidates[slot][0]
            if action not in legal:
                raise ValueError('Teacher action is not legal in the environment')
            targets.append(legal.index(action))
        features, padding = _batch([rows for _, rows in candidates], device)
        logits = model(features, padding)
        losses.append(nn.functional.cross_entropy(logits, torch.tensor(targets, device=device), reduction='sum'))
        for slot, k in enumerate(active):
            envs[k].step(teacher_actions[k][steps[k]])
            steps[k] += 1
    return torch.stack(losses).sum() / sum(len(a) for a in teacher_actions)


def reinforce_loss(model: AttentionPolicy, problems: list[tuple[ParallelMaintenanceInstance, str]], *,
                   samples: int, generator: torch.Generator, device: str = 'cpu',
                   scale: list[float] | None = None) -> tuple[torch.Tensor, float]:
    """REINFORCE with the per-problem mean of ``samples`` rollouts as baseline.

    ``scale`` divides each problem's advantages (e.g. its teacher value + 1)
    so large-tardiness instances do not dominate. Returns (loss, mean T).
    """
    tardiness, log_prob = rollout(model, problems, samples=samples, greedy=False, generator=generator,
                                  device=device, track_gradients=True)
    values = torch.tensor(tardiness, dtype=torch.float32, device=device)
    advantage = values - values.mean(dim=1, keepdim=True)
    if scale is not None:
        advantage = advantage / torch.tensor(scale, dtype=torch.float32, device=device).unsqueeze(1)
    loss = (advantage.flatten() * log_prob).mean()
    return loss, float(values.mean())


def save(model: AttentionPolicy, path: Path) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({'config': model.config.__dict__, 'state': model.state_dict()}, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, *, expected_sha256: str | None = None, device: str = 'cpu') -> AttentionPolicy:
    path = Path(path)
    if expected_sha256 is not None and hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('Checkpoint hash mismatch')
    payload = torch.load(path, map_location=device, weights_only=True)
    model = AttentionPolicy(PolicyConfig(**payload['config'])).to(device)
    model.load_state_dict(payload['state'])
    model.eval()
    return model
