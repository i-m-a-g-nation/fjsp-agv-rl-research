"""Shared per-action scoring MLP (NumPy) and masked episode rollout.

score(a) = w2 . tanh(W1 x_a + b1); the policy is a softmax over the legal
actions only, so masked actions never receive probability or gradient.
Every returned plan comes from the R1 environment, which G1-checks it.
"""

from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path

import numpy as np

from src.graduation.action_features import FEATURE_COUNT, action_candidates
from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.result import MaintenanceScheduleResult
from src.graduation.rl_environment import EpisodeInvariantError, ParallelMaintenanceEnv

PARAMETERS = ('W1', 'b1', 'w2')


@dataclass(frozen=True)
class Decision:
    """One step: candidate features, hidden activations, probabilities, choice."""
    features: np.ndarray
    hidden: np.ndarray
    probabilities: np.ndarray
    choice: int


@dataclass(frozen=True)
class Episode:
    result: MaintenanceScheduleResult
    total_tardiness: int
    decisions: tuple[Decision, ...]


class ScoringPolicy:
    def __init__(self, *, seed: int, hidden_size: int = 32):
        if type(seed) is not int or type(hidden_size) is not int or hidden_size < 1:
            raise ValueError('seed and hidden_size must be integers; hidden_size >= 1')
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0.0, 1.0 / math.sqrt(FEATURE_COUNT), (hidden_size, FEATURE_COUNT))
        self.b1 = np.zeros(hidden_size)
        self.w2 = rng.normal(0.0, 1.0 / math.sqrt(hidden_size), hidden_size)
        self._adam_m = {name: np.zeros_like(getattr(self, name)) for name in PARAMETERS}
        self._adam_v = {name: np.zeros_like(getattr(self, name)) for name in PARAMETERS}
        self._adam_t = 0

    def forward(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if features.ndim != 2 or features.shape[1] != FEATURE_COUNT or not len(features):
            raise ValueError('features must be a nonempty (k, FEATURE_COUNT) array')
        hidden = np.tanh(features @ self.W1.T + self.b1)
        scores = hidden @ self.w2
        scores = scores - scores.max()
        probabilities = np.exp(scores)
        probabilities /= probabilities.sum()
        if not np.all(np.isfinite(probabilities)):
            raise FloatingPointError('Non-finite action probabilities')
        return hidden, probabilities

    def grad_log_probability(self, decision: Decision) -> dict[str, np.ndarray]:
        """Gradient of log pi(choice) over the legal candidates."""
        g = -decision.probabilities.copy()
        g[decision.choice] += 1.0
        dz = np.outer(g, self.w2) * (1.0 - decision.hidden ** 2)
        return {'W1': dz.T @ decision.features, 'b1': dz.sum(axis=0), 'w2': decision.hidden.T @ g}

    def ascend(self, gradients: dict[str, np.ndarray], learning_rate: float,
               beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8) -> None:
        """One Adam step that increases the objective whose gradient is given."""
        if set(gradients) != set(PARAMETERS) or not learning_rate > 0:
            raise ValueError('Expected gradients for every parameter and a positive learning rate')
        self._adam_t += 1
        for name in PARAMETERS:
            g = gradients[name]
            if not np.all(np.isfinite(g)):
                raise FloatingPointError(f'Non-finite gradient for {name}')
            self._adam_m[name] = beta1 * self._adam_m[name] + (1 - beta1) * g
            self._adam_v[name] = beta2 * self._adam_v[name] + (1 - beta2) * g * g
            m_hat = self._adam_m[name] / (1 - beta1 ** self._adam_t)
            v_hat = self._adam_v[name] / (1 - beta2 ** self._adam_t)
            setattr(self, name, getattr(self, name) + learning_rate * m_hat / (np.sqrt(v_hat) + eps))

    def state_dict(self) -> dict[str, np.ndarray]:
        return {name: getattr(self, name).copy() for name in PARAMETERS}

    def load_state(self, state: dict[str, np.ndarray]) -> None:
        if set(state) != set(PARAMETERS):
            raise ValueError('State must contain exactly W1, b1 and w2')
        for name in PARAMETERS:
            value = np.asarray(state[name], dtype=np.float64)
            if value.shape != getattr(self, name).shape or not np.all(np.isfinite(value)):
                raise ValueError(f'Invalid {name} shape or values')
            setattr(self, name, value.copy())

    def save(self, path: Path) -> str:
        """Write an .npz checkpoint and return its SHA-256."""
        buffer = io.BytesIO()
        np.savez(buffer, **self.state_dict())
        Path(path).write_bytes(buffer.getvalue())
        return hashlib.sha256(buffer.getvalue()).hexdigest()

    @classmethod
    def load(cls, path: Path, *, expected_sha256: str | None = None) -> 'ScoringPolicy':
        raw = Path(path).read_bytes()
        if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError('Checkpoint hash mismatch')
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            state = {name: archive[name] for name in archive.files}
        policy = cls(seed=0, hidden_size=state['w2'].shape[0])
        policy.load_state(state)
        return policy


def run_episode(policy: ScoringPolicy, data: ParallelMaintenanceInstance, *, mode: str,
                rng: np.random.Generator | None = None, record: bool = False) -> Episode:
    """Greedy when rng is None, otherwise sample; only legal actions are scored."""
    env = ParallelMaintenanceEnv(data, mode=mode)
    decisions = []
    for _ in range(len(data.tasks) + data.num_machines):
        legal, features = action_candidates(env)
        hidden, probabilities = policy.forward(features)
        choice = int(np.argmax(probabilities)) if rng is None else int(rng.choice(len(legal), p=probabilities))
        if record:
            decisions.append(Decision(features, hidden, probabilities, choice))
        step = env.step(legal[choice])
        if step.terminated:
            return Episode(step.result, step.result.total_tardiness, tuple(decisions))
    raise EpisodeInvariantError('Policy did not terminate within n+m steps')
