"""Attention scoring policy (PyTorch) on a construction MDP.

Each step featurizes every legal action, lets the candidates attend to each
other with a small Transformer encoder, and scores them; illegal actions
never enter the softmax, so every finished episode is a checker-accepted plan
from the environment. Episodes run in lockstep so one forward pass serves
every active environment. Two MDPs are supported (``PolicyConfig.kind``):

* ``'action'``: ``env.ParallelMaintenanceEnv`` (job x machine actions, 19 features);
* ``'sequence'``: ``sequence_env.SequenceEnv`` (next decoder token, 20 features),
  which keeps the candidate set at about n + m for large instances.

Training: behaviour cloning on teacher states (replayed once, possibly in
parallel processes, then shuffled into large state mini-batches), then
REINFORCE with a shared per-instance baseline (mean return of the K sampled
rollouts of that instance, as in POMO). No PPO, no value network. REINFORCE
samples without keeping the graph and re-scores the recorded states in
chunks, so memory does not grow with the episode length; the gradient is
the same as for the whole-episode loss.

This module needs PyTorch; the rest of the project does not import it.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
import torch
from torch import nn

from fjsp_lab.maintenance.env import ParallelMaintenanceEnv
from fjsp_lab.maintenance.features import FEATURE_COUNT, action_candidates
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.sequence_env import SEQUENCE_FEATURE_COUNT, SequenceEnv

Problem = tuple[ParallelMaintenanceInstance, str]


@dataclass(frozen=True)
class PolicyConfig:
    width: int = 128
    layers: int = 3
    heads: int = 8
    feedforward: int = 256
    kind: str = 'action'
    features: int = FEATURE_COUNT


def config_for(kind: str, **kwargs) -> PolicyConfig:
    features = {'action': FEATURE_COUNT, 'sequence': SEQUENCE_FEATURE_COUNT}[kind]
    return PolicyConfig(kind=kind, features=features, **kwargs)


class AttentionPolicy(nn.Module):
    def __init__(self, config: PolicyConfig = PolicyConfig()):
        super().__init__()
        self.config = config
        self.embed = nn.Linear(config.features, config.width)
        layer = nn.TransformerEncoderLayer(config.width, config.heads, config.feedforward, dropout=0.0,
                                           batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, config.layers, enable_nested_tensor=False)
        self.head = nn.Sequential(nn.LayerNorm(config.width), nn.Linear(config.width, 1))

    def forward(self, features: torch.Tensor, padding: torch.Tensor) -> torch.Tensor:
        """features [E, C, F], padding [E, C] (True = no candidate) -> logits [E, C]."""
        hidden = self.encoder(self.embed(features), src_key_padding_mask=padding)
        return self.head(hidden).squeeze(-1).masked_fill(padding, float('-inf'))


def make_env(kind: str, data: ParallelMaintenanceInstance, mode: str):
    if kind == 'action':
        return ParallelMaintenanceEnv(data, mode=mode)
    if kind == 'sequence':
        return SequenceEnv(data, mode=mode)
    raise ValueError("kind must be 'action' or 'sequence'")


def candidates(env) -> tuple[list[int], np.ndarray]:
    return action_candidates(env) if isinstance(env, ParallelMaintenanceEnv) else env.candidates()


def precision(device) -> object:
    """bf16 autocast on CUDA (softmax and losses stay in float32); full precision on the CPU."""
    return torch.autocast('cuda', dtype=torch.bfloat16) if str(device).startswith('cuda') else nullcontext()


def _batch(rows: list[np.ndarray], device) -> tuple[torch.Tensor, torch.Tensor]:
    width = max(len(r) for r in rows)
    features = np.zeros((len(rows), width, rows[0].shape[1]), dtype=np.float32)
    padding = np.ones((len(rows), width), dtype=bool)
    for k, r in enumerate(rows):
        features[k, :len(r)] = r
        padding[k, :len(r)] = False
    return torch.from_numpy(features).to(device), torch.from_numpy(padding).to(device)


def _run(model: AttentionPolicy, problems: list[Problem], samples: int, greedy: bool,
         generator: torch.Generator | None, device: str, record: bool):
    """Lockstep episodes; optionally record (features, padding, active, choice) per step."""
    envs = [make_env(model.config.kind, data, mode) for data, mode in problems for _ in range(samples)]
    tardiness, steps = [None] * len(envs), []
    with torch.no_grad():
        while True:
            active = [k for k, env in enumerate(envs) if not env.done]
            if not active:
                break
            options = [candidates(envs[k]) for k in active]
            features, padding = _batch([rows for _, rows in options], device)
            with precision(device):
                logits = model(features, padding).float()
            if greedy:
                choice = logits.argmax(dim=-1)
            else:
                probabilities = torch.softmax(logits, dim=-1).float().cpu()
                choice = torch.multinomial(probabilities, 1, generator=generator).squeeze(-1).to(device)
            if record:
                steps.append((features, padding, torch.tensor(active, device=device), choice))
            for slot, (k, picked) in enumerate(zip(active, choice.tolist())):
                step = envs[k].step(options[slot][0][picked])
                if step.terminated:
                    tardiness[k] = step.result.total_tardiness
    if any(t is None for t in tardiness):
        raise RuntimeError('An episode did not terminate')
    return [tardiness[p * samples:(p + 1) * samples] for p in range(len(problems))], steps


def rollout(model: AttentionPolicy, problems: list[Problem], *, samples: int, greedy: bool,
            generator: torch.Generator | None = None, device: str = 'cpu') -> tuple[list[list[int]], None]:
    """Run ``samples`` episodes per problem; returns (tardiness[problem][sample], None)."""
    tardiness, _ = _run(model, problems, samples, greedy, generator, device, record=False)
    return tardiness, None


@dataclass
class StateDataset:
    """Teacher states of many episodes: candidate rows, per-state offsets and the teacher's index."""

    rows: np.ndarray       # [total candidates, F] float16
    offsets: np.ndarray    # [states + 1]
    targets: np.ndarray    # [states]

    def __len__(self) -> int:
        return len(self.targets)

    @classmethod
    def concatenate(cls, parts: list[tuple[list[np.ndarray], list[int]]]) -> 'StateDataset':
        arrays = [a for states, _ in parts for a in states]
        sizes = np.array([len(a) for a in arrays], dtype=np.int64)
        return cls(np.concatenate(arrays).astype(np.float16), np.concatenate(([0], np.cumsum(sizes))),
                   np.array([t for _, targets in parts for t in targets], dtype=np.int64))

    def batch(self, indices: np.ndarray, device) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        states = [self.rows[self.offsets[i]:self.offsets[i + 1]] for i in indices]
        features, padding = _batch(states, device)
        return features, padding, torch.from_numpy(self.targets[indices]).to(device)


def teacher_states(kind: str, problem: Problem, actions: list[int]) -> tuple[list[np.ndarray], list[int]]:
    """Replay one teacher episode; returns each state's candidate rows and the teacher's index (no torch)."""
    env = make_env(kind, *problem)
    states, targets = [], []
    for action in actions:
        legal, rows = candidates(env)
        if action not in legal:
            raise ValueError('Teacher action is not legal in the environment')
        states.append(rows.astype(np.float32))
        targets.append(legal.index(action))
        env.step(action)
    if not env.done:
        raise ValueError('Teacher actions do not finish the episode')
    return states, targets


def imitation_minibatch(model: AttentionPolicy, dataset: StateDataset, indices: np.ndarray,
                        device: str = 'cpu') -> float:
    """Back-propagate the mean teacher cross-entropy over the given states; returns its value."""
    features, padding, targets = dataset.batch(indices, device)
    with precision(device):
        logits = model(features, padding)
    loss = nn.functional.cross_entropy(logits.float(), targets)
    loss.backward()
    return loss.item()


def reinforce_step(model: AttentionPolicy, problems: list[Problem], *, samples: int, generator: torch.Generator,
                   device: str = 'cpu', scale: list[float] | None = None, chunk_rows: int = 4096) -> float:
    """Accumulate REINFORCE gradients with the per-problem mean of ``samples`` rollouts as baseline.

    ``scale`` divides each problem's advantages (e.g. its teacher value + 1)
    so large-tardiness instances do not dominate. The recorded states are
    re-scored in chunks of up to ``chunk_rows`` states (one forward/backward
    per chunk); the gradient equals that of the whole-episode loss. Returns
    the mean sampled T.
    """
    tardiness, steps = _run(model, problems, samples, False, generator, device, record=True)
    values = torch.tensor(tardiness, dtype=torch.float32, device=device)
    advantage = values - values.mean(dim=1, keepdim=True)
    if scale is not None:
        advantage = advantage / torch.tensor(scale, dtype=torch.float32, device=device).unsqueeze(1)
    advantage = advantage.flatten()
    episodes = advantage.numel()
    chunk = []
    for index, step in enumerate(steps):
        chunk.append(step)
        if sum(len(item[2]) for item in chunk) >= chunk_rows or index == len(steps) - 1:
            width = max(item[0].shape[1] for item in chunk)
            features = torch.cat([nn.functional.pad(f, (0, 0, 0, width - f.shape[1])) for f, *_ in chunk])
            padding = torch.cat([nn.functional.pad(m, (0, width - m.shape[1]), value=True) for _, m, *_ in chunk])
            active = torch.cat([item[2] for item in chunk])
            choice = torch.cat([item[3] for item in chunk])
            with precision(device):
                logits = model(features, padding)
            picked = torch.log_softmax(logits.float(), dim=-1).gather(1, choice.unsqueeze(1)).squeeze(1)
            ((advantage[active] * picked).sum() / episodes).backward()
            chunk = []
    return float(values.mean())


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
