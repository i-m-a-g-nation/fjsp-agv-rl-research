"""Per-action scoring MLP (NumPy), trained by behaviour cloning then REINFORCE.

score(a) = w2 . tanh(W1 x_a + b1); the policy is a softmax over the legal
actions only, so masked actions never receive probability or gradient.
Every returned plan comes from the construction environment, which checks it.

Training first imitates, per instance, the best of the EDD/MDD/ATC rules,
then fine-tunes with self-critical REINFORCE (greedy rollout as baseline,
advantage = (T_greedy - T_sample) / max(1, T_greedy)). The validation split
alone selects the checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
import statistics

import numpy as np

from fjsp_lab.maintenance.env import EpisodeInvariantError, ParallelMaintenanceEnv
from fjsp_lab.maintenance.features import FEATURE_COUNT, action_candidates
from fjsp_lab.maintenance.generator import SampledInstance
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.rules import DISPATCH_RULES, rule_action, solve_dispatch_rule
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult

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
    for _ in range(env.total_steps):
        legal, features = action_candidates(env)
        hidden, probabilities = policy.forward(features)
        choice = int(np.argmax(probabilities)) if rng is None else int(rng.choice(len(legal), p=probabilities))
        if record:
            decisions.append(Decision(features, hidden, probabilities, choice))
        step = env.step(legal[choice])
        if step.terminated:
            return Episode(step.result, step.result.total_tardiness, tuple(decisions))
    raise EpisodeInvariantError('Policy did not terminate within n+m steps')


def best_of_rollouts(policy: ScoringPolicy, data: ParallelMaintenanceInstance, *, mode: str,
                     samples: int, seed: int) -> MaintenanceScheduleResult:
    """Greedy plus ``samples`` sampled rollouts; return the plan with least tardiness.

    Uses 1 + samples rollouts. Ties keep the earliest rollout (greedy first).
    """
    if type(samples) is not int or samples < 0 or type(seed) is not int:
        raise ValueError('samples must be a nonnegative integer and seed an integer')
    best = run_episode(policy, data, mode=mode)
    rng = np.random.default_rng(seed)
    for _ in range(samples):
        episode = run_episode(policy, data, mode=mode, rng=rng)
        if episode.total_tardiness < best.total_tardiness:
            best = episode
    return best.result


# --- training ---------------------------------------------------------------

def rule_tardiness(instance: SampledInstance) -> dict[str, int]:
    return {rule: solve_dispatch_rule(instance.data, mode=instance.mode, rule=rule).total_tardiness
            for rule in DISPATCH_RULES}


def mean_greedy_tardiness(policy: ScoringPolicy, instances: list[SampledInstance]) -> float:
    return statistics.fmean(run_episode(policy, i.data, mode=i.mode).total_tardiness for i in instances)


def imitation_samples(instances: list[SampledInstance]) -> list[tuple[np.ndarray, int]]:
    """Feature rows and choices along each instance's best-rule trajectory."""
    samples = []
    for instance in instances:
        scores = rule_tardiness(instance)
        teacher = min(DISPATCH_RULES, key=lambda rule: scores[rule])
        env = ParallelMaintenanceEnv(instance.data, mode=instance.mode)
        while True:
            legal, features = action_candidates(env)
            action = rule_action(env, legal, teacher)
            samples.append((features, legal.index(action)))
            if env.step(action).terminated:
                break
    return samples


def _zero(policy):
    return {name: np.zeros_like(getattr(policy, name)) for name in PARAMETERS}


def behaviour_cloning_epoch(policy: ScoringPolicy, samples: list, *, rng: np.random.Generator,
                            learning_rate: float, batch_size: int = 64) -> float:
    """One shuffled pass maximizing log-likelihood; returns mean negative log-likelihood."""
    order = rng.permutation(len(samples))
    losses = []
    for start in range(0, len(order), batch_size):
        batch = order[start:start + batch_size]
        total = _zero(policy)
        for index in batch:
            features, choice = samples[index]
            hidden, probabilities = policy.forward(features)
            losses.append(-np.log(max(probabilities[choice], 1e-300)))
            for name, g in policy.grad_log_probability(Decision(features, hidden, probabilities, choice)).items():
                total[name] += g
        policy.ascend({name: g / len(batch) for name, g in total.items()}, learning_rate)
    return float(np.mean(losses))


def reinforce_epoch(policy: ScoringPolicy, instances: list[SampledInstance], *, rng: np.random.Generator,
                    learning_rate: float, batch_size: int = 16, samples_per_instance: int = 4) -> float:
    """Self-critical REINFORCE pass; returns the mean sampled tardiness."""
    order = rng.permutation(len(instances))
    sampled = []
    for start in range(0, len(order), batch_size):
        total, count = _zero(policy), 0
        for index in order[start:start + batch_size]:
            instance = instances[index]
            baseline = run_episode(policy, instance.data, mode=instance.mode).total_tardiness
            for _ in range(samples_per_instance):
                episode = run_episode(policy, instance.data, mode=instance.mode, rng=rng, record=True)
                sampled.append(episode.total_tardiness)
                count += 1
                advantage = (baseline - episode.total_tardiness) / max(1.0, baseline)
                if advantage == 0:
                    continue
                for decision in episode.decisions:
                    for name, g in policy.grad_log_probability(decision).items():
                        total[name] += advantage * g
        policy.ascend({name: g / count for name, g in total.items()}, learning_rate)
    return float(np.mean(sampled))


def train(train_set: list[SampledInstance], val_set: list[SampledInstance], *, seed: int, hidden_size: int = 32,
          bc_epochs: int = 15, bc_learning_rate: float = 3e-3, rl_epochs: int = 12,
          rl_learning_rate: float = 1e-3, log=None) -> tuple[ScoringPolicy, list[dict]]:
    """Train and return the policy restored to its best validation checkpoint plus the log."""
    rng = np.random.default_rng(seed)
    policy = ScoringPolicy(seed=seed, hidden_size=hidden_size)
    history = [{'phase': 'init', 'epoch': 0, 'val_mean_tardiness': mean_greedy_tardiness(policy, val_set)}]
    best = (history[0]['val_mean_tardiness'], policy.state_dict(), 'init', 0)
    samples = imitation_samples(train_set)

    def checkpoint(phase, epoch, metric_name, metric):
        nonlocal best
        val = mean_greedy_tardiness(policy, val_set)
        history.append({'phase': phase, 'epoch': epoch, metric_name: metric, 'val_mean_tardiness': val})
        if log is not None:
            log(history[-1])
        if val < best[0]:
            best = (val, policy.state_dict(), phase, epoch)

    for epoch in range(1, bc_epochs + 1):
        loss = behaviour_cloning_epoch(policy, samples, rng=rng, learning_rate=bc_learning_rate)
        checkpoint('bc', epoch, 'train_nll', loss)
    for epoch in range(1, rl_epochs + 1):
        rate = rl_learning_rate * (1 - (epoch - 1) / rl_epochs)
        sampled = reinforce_epoch(policy, train_set, rng=rng, learning_rate=rate)
        checkpoint('rl', epoch, 'train_sampled_tardiness', sampled)
    policy.load_state(best[1])
    history.append({'phase': 'selected', 'source_phase': best[2], 'epoch': best[3], 'val_mean_tardiness': best[0]})
    return policy, history
