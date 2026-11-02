"""L2 learned policy: per-candidate scoring MLP (NumPy), imitation then REINFORCE.

Every simulator decision point offers candidates (job, destination,
vehicle; or stay). Each candidate gets a feature row (``FEATURE_NAMES``; times
divided by the scale S = total minimum processing time / machines), a
two-layer MLP scores it, and a softmax over the unmasked candidates gives the
policy. Deadlock avoidance is the mask: a candidate drawn (greedy: the most
likely) is checked with the simulator's lookahead (``is_safe``); if unsafe it
is masked and the distribution renormalized; if every candidate is masked the
simulator waits. With unlimited buffers nothing is checked. Gradients use
the renormalized distribution, so masked candidates receive none.

Training (``train``): behaviour cloning on the decisions of the best of the
four avoided rules per training instance, then REINFORCE with a shared
baseline (mean makespan of the K samples of the same instance), Adam. The
checkpoint is chosen on the validation set only, by the mean ratio of the
greedy makespan to the instance's best avoided rule. Every episode's
schedule passes the checker (the simulator returns only accepted schedules).
Design: docs/plans/innovation_rl_design.md.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from fjsp_lab.logistics.instance import LogisticsInstance
from fjsp_lab.logistics.rules import RULES, rule_policy
from fjsp_lab.logistics.schedule import LogisticsSchedule
from fjsp_lab.logistics.simulator import Candidate, LogisticsSimulator, is_safe

FEATURE_NAMES = (
    'is_stay', 'is_home', 'empty_travel', 'loaded_travel', 'wait_for_machine', 'processing', 'finish',
    'finish_rank', 'job_remaining_work', 'job_remaining_ops', 'job_waited', 'destination_occupancy',
    'destination_full_after', 'destination_busy', 'destination_queue', 'origin_queue', 'idle_vehicles',
    'done_jobs', 'blocking', 'finite_buffer',
)
FEATURE_COUNT = len(FEATURE_NAMES)
COLUMN = {name: index for index, name in enumerate(FEATURE_NAMES)}
PARAMETERS = ('W1', 'b1', 'w2')
CLIP = 5.0


def scale(instance: LogisticsInstance) -> float:
    """S = total minimum processing time / number of machines (at least 1)."""
    work = sum(min(p for _, p in op.machine_options) for job in instance.production.jobs for op in job.operations)
    return max(1.0, work / instance.num_machines)


def candidate_features(sim: LogisticsSimulator, options: Sequence[Candidate], unit: float) -> np.ndarray:
    """One feature row per candidate (same order as ``options``)."""
    instance, production = sim.instance, sim.instance.production
    n, lu = production.num_jobs, instance.lu
    rows = np.zeros((len(options), FEATURE_COUNT))
    finishes = np.array([c.finish for c in options], dtype=float)
    order = finishes.argsort(kind='stable').argsort()
    span = max(1, len(options) - 1)
    idle = sum(free <= sim.now for free in sim.vehicle_free) / instance.num_vehicles
    done = sum(sim.done) / n
    max_ops = max(job.num_ops for job in production.jobs)
    for i, c in enumerate(options):
        job = production.jobs[c.job]
        x = rows[i]
        x[COLUMN['is_stay']] = c.vehicle is None
        x[COLUMN['is_home']] = c.machine == lu
        x[COLUMN['empty_travel']] = (c.pickup - sim.now) / unit
        x[COLUMN['loaded_travel']] = (c.delivery - c.pickup) / unit
        x[COLUMN['wait_for_machine']] = (max(c.delivery, c.machine_ready) - c.delivery) / unit
        x[COLUMN['processing']] = c.processing_time / unit
        x[COLUMN['finish']] = (c.finish - sim.now) / unit
        x[COLUMN['finish_rank']] = order[i] / span
        x[COLUMN['job_remaining_work']] = sum(min(p for _, p in job.operations[o].machine_options)
                                              for o in range(sim.next_op[c.job], job.num_ops)) / unit
        x[COLUMN['job_remaining_ops']] = (job.num_ops - sim.next_op[c.job]) / max_ops
        x[COLUMN['job_waited']] = (sim.now - sim.ready[c.job]) / unit
        if c.machine != lu:
            capacity = instance.station_capacity(c.machine)
            if capacity is not None:
                x[COLUMN['destination_occupancy']] = sim.places[c.machine] / capacity
                x[COLUMN['destination_full_after']] = sim.places[c.machine] + (c.vehicle is not None) >= capacity
                x[COLUMN['finite_buffer']] = 1.0
            x[COLUMN['destination_busy']] = sim.holder[c.machine] is not None
            x[COLUMN['destination_queue']] = len(sim.queue[c.machine]) / n
        origin = sim.location[c.job]
        if origin is not None and origin != lu:
            x[COLUMN['origin_queue']] = len(sim.queue[origin]) / n
        x[COLUMN['idle_vehicles']] = idle
        x[COLUMN['done_jobs']] = done
        x[COLUMN['blocking']] = instance.blocking
    np.clip(rows, -CLIP, CLIP, out=rows)
    return rows


@dataclass(frozen=True)
class Decision:
    features: np.ndarray
    hidden: np.ndarray
    probabilities: np.ndarray        # renormalized over the unmasked candidates (masked = 0)
    choice: int


@dataclass(frozen=True)
class Episode:
    schedule: LogisticsSchedule
    makespan: int
    decisions: tuple[Decision, ...]


class LogisticsPolicy:
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

    def forward(self, features: np.ndarray, mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Hidden activations and the softmax over the unmasked candidates."""
        if features.ndim != 2 or features.shape[1] != FEATURE_COUNT or not len(features):
            raise ValueError('features must be a nonempty (k, FEATURE_COUNT) array')
        hidden = np.tanh(features @ self.W1.T + self.b1)
        scores = hidden @ self.w2
        if mask is not None:
            scores = np.where(mask, scores, -np.inf)
        scores = scores - scores.max()
        probabilities = np.exp(scores)
        probabilities /= probabilities.sum()
        if not np.all(np.isfinite(probabilities)):
            raise FloatingPointError('Non-finite action probabilities')
        return hidden, probabilities

    def grad_log_probability(self, decision: Decision) -> dict[str, np.ndarray]:
        """Gradient of log pi(choice) over the unmasked candidates."""
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
    def load(cls, path: Path, *, expected_sha256: str | None = None) -> LogisticsPolicy:
        raw = Path(path).read_bytes()
        if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError('Checkpoint hash mismatch')
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            state = {name: archive[name] for name in archive.files}
        policy = cls(seed=0, hidden_size=state['w2'].shape[0])
        policy.load_state(state)
        return policy


def run_episode(policy: LogisticsPolicy, instance: LogisticsInstance, *, rng: np.random.Generator | None = None,
                record: bool = False) -> Episode:
    """Greedy when ``rng`` is None, otherwise sampled; unsafe candidates are masked as drawn."""
    unit = scale(instance)
    finite = any(capacity is not None for capacity in instance.buffer_capacity)
    decisions: list[Decision] = []

    def act(sim: LogisticsSimulator, options: list[Candidate]) -> Candidate | None:
        features = candidate_features(sim, options, unit)
        mask = np.ones(len(options), dtype=bool)
        while mask.any():
            hidden, probabilities = policy.forward(features, mask)
            index = int(probabilities.argmax()) if rng is None else int(rng.choice(len(options), p=probabilities))
            if not finite or is_safe(sim, options[index]):
                if record:
                    decisions.append(Decision(features, hidden, probabilities, index))
                return options[index]
            mask[index] = False
        return None

    schedule = LogisticsSimulator(instance).run(act)
    return Episode(schedule, schedule.makespan, tuple(decisions))


def best_rule(instance: LogisticsInstance) -> tuple[str, int]:
    """(rule, makespan) of the best of the four avoided rules."""
    results = [(LogisticsSimulator(instance).run(rule_policy(rule, avoid_deadlock=True)).makespan, rule)
               for rule in RULES[:4]]
    makespan, rule = min(results)
    return rule, makespan


def imitation_samples(instances: Sequence[LogisticsInstance]) -> list[tuple[np.ndarray, int]]:
    """(features, chosen index) at every decision of each instance's best avoided rule."""
    samples = []
    for instance in instances:
        rule, _ = best_rule(instance)
        guarded, unit = rule_policy(rule, avoid_deadlock=True), scale(instance)

        def recording(sim: LogisticsSimulator, options: list[Candidate]) -> Candidate | None:
            choice = guarded(sim, options)
            if choice is not None:
                samples.append((candidate_features(sim, options, unit), options.index(choice)))
            return choice

        LogisticsSimulator(instance).run(recording)
    return samples


def _zero(policy: LogisticsPolicy) -> dict[str, np.ndarray]:
    return {name: np.zeros_like(getattr(policy, name)) for name in PARAMETERS}


def behaviour_cloning_epoch(policy: LogisticsPolicy, samples: list[tuple[np.ndarray, int]], *,
                            rng: np.random.Generator, learning_rate: float, batch_size: int = 64) -> float:
    """One shuffled pass maximizing log-likelihood; returns the mean negative log-likelihood."""
    order = rng.permutation(len(samples))
    losses = []
    for start in range(0, len(order), batch_size):
        batch = order[start:start + batch_size]
        total = _zero(policy)
        for index in batch:
            features, choice = samples[index]
            hidden, probabilities = policy.forward(features)
            losses.append(-math.log(max(probabilities[choice], 1e-300)))
            for name, g in policy.grad_log_probability(Decision(features, hidden, probabilities, choice)).items():
                total[name] += g
        policy.ascend({name: g / len(batch) for name, g in total.items()}, learning_rate)
    return float(np.mean(losses))


def reinforce_epoch(policy: LogisticsPolicy, instances: Sequence[LogisticsInstance], *,
                    rng: np.random.Generator, learning_rate: float, batch_size: int = 8,
                    samples_per_instance: int = 4) -> float:
    """REINFORCE with the shared per-instance baseline; returns the mean sampled makespan / instance scale."""
    order = rng.permutation(len(instances))
    ratios = []
    for start in range(0, len(order), batch_size):
        total, count = _zero(policy), 0
        for index in order[start:start + batch_size]:
            episodes = [run_episode(policy, instances[index], rng=rng, record=True)
                        for _ in range(samples_per_instance)]
            baseline = float(np.mean([e.makespan for e in episodes]))
            unit = scale(instances[index])
            for episode in episodes:
                ratios.append(episode.makespan / unit)
                advantage = (baseline - episode.makespan) / baseline
                count += 1
                if advantage == 0:
                    continue
                for decision in episode.decisions:
                    for name, g in policy.grad_log_probability(decision).items():
                        total[name] += advantage * g
        if count:
            policy.ascend({name: g / count for name, g in total.items()}, learning_rate)
    return float(np.mean(ratios))


def mean_ratio(policy: LogisticsPolicy, instances: Sequence[LogisticsInstance], references: Sequence[int]) -> float:
    """Mean greedy makespan / reference makespan (e.g. the best avoided rule)."""
    return float(np.mean([run_episode(policy, instance).makespan / reference
                          for instance, reference in zip(instances, references)]))


def train(train_set: Sequence[LogisticsInstance], val_set: Sequence[LogisticsInstance], *, seed: int,
          hidden_size: int = 32, bc_epochs: int = 10, bc_learning_rate: float = 3e-3, rl_epochs: int = 10,
          rl_learning_rate: float = 1e-3, samples_per_instance: int = 4, rl_batch_size: int = 8,
          log: Callable[[dict], None] | None = None) -> tuple[LogisticsPolicy, list[dict]]:
    """Train; return the policy restored to its best validation checkpoint and the history."""
    rng = np.random.default_rng(seed)
    policy = LogisticsPolicy(seed=seed, hidden_size=hidden_size)
    references = [best_rule(instance)[1] for instance in val_set]
    history = [{'phase': 'init', 'epoch': 0, 'val_ratio_to_best_rule': mean_ratio(policy, val_set, references)}]
    best = (history[0]['val_ratio_to_best_rule'], policy.state_dict(), 'init', 0)

    def checkpoint(phase: str, epoch: int, name: str, value: float) -> None:
        nonlocal best
        val = mean_ratio(policy, val_set, references)
        history.append({'phase': phase, 'epoch': epoch, name: value, 'val_ratio_to_best_rule': val})
        if log is not None:
            log(history[-1])
        if val < best[0]:
            best = (val, policy.state_dict(), phase, epoch)

    samples = imitation_samples(train_set)
    for epoch in range(1, bc_epochs + 1):
        checkpoint('imitation', epoch, 'loss', behaviour_cloning_epoch(policy, samples, rng=rng,
                                                                       learning_rate=bc_learning_rate))
    for epoch in range(1, rl_epochs + 1):
        checkpoint('reinforce', epoch, 'train_sampled_makespan_over_scale', reinforce_epoch(
            policy, train_set, rng=rng, learning_rate=rl_learning_rate, batch_size=rl_batch_size,
            samples_per_instance=samples_per_instance))
    policy.load_state(best[1])
    history.append({'phase': 'selected', 'epoch': best[3], 'from': best[2], 'val_ratio_to_best_rule': best[0]})
    return policy, history
