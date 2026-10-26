"""Finite masked REINFORCE baseline; validation alone selects checkpoints.

The objective, reward=-total_tardiness/100, and gamma=1 are inherited from R1.
This small NumPy baseline makes no claim to be PPO or the final research model.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

import numpy as np

from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.neural_policy import MaskedMLP, PolicySample, policy_features
from src.graduation.result import MaintenanceScheduleResult
from src.graduation.rl_environment import (
    ACTION_COUNT, REWARD_SCALE, EpisodeInvariantError, ParallelMaintenanceEnv,
)
from src.graduation.state_encoding import encode_construction_observation


@dataclass(frozen=True)
class PolicyEpisode:
    """Only a complete, independently checked trajectory becomes an episode."""

    actions: tuple[int, ...]
    rewards: tuple[float, ...]
    total_reward: float
    result: MaintenanceScheduleResult
    samples: tuple[PolicySample, ...]
    transitions: tuple[dict, ...]


def base_instance_identity(data: ParallelMaintenanceInstance) -> str:
    """Bind the ordered (processing time, due date) tasks, excluding conditions."""
    if not isinstance(data, ParallelMaintenanceInstance):
        raise ValueError('Expected typed parallel-maintenance data')
    payload = [[task.processing_time, task.due_date] for task in data.tasks]
    return hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode('utf-8')).hexdigest()


def _integer(value, name, minimum, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{name} must be an integer in the supported range')


def _callback(value, name):
    if value is not None and not callable(value):
        raise ValueError(f'{name} must be callable or None')


def _deadline_budget(check_budget):
    _callback(check_budget, 'check_budget')
    started = time.monotonic()

    def check():
        if time.monotonic() - started >= 120:
            raise TimeoutError('Policy training exceeded the internal 120 second budget')
        if check_budget is not None:
            check_budget()

    return check


def run_policy_episode(
    data: ParallelMaintenanceInstance, *, mode: str, actor: MaskedMLP, seed: int,
    deterministic: bool = False, check_budget: Callable[[], None] | None = None,
) -> PolicyEpisode:
    """Roll out one local RNG stream without changing the actor's parameters.

    Every action uses the original exact mask. Exceptions propagate; there is
    no repair, partial accepted result, or optimizer call on an interrupted run.
    """
    _integer(seed, 'seed', 0, 2**32 - 1)
    if type(deterministic) is not bool or not isinstance(actor, MaskedMLP):
        raise ValueError('Expected a MaskedMLP actor and boolean deterministic flag')
    budget = _deadline_budget(check_budget)
    env = ParallelMaintenanceEnv(data, mode=mode)
    observation = env.reset()
    rng = np.random.Generator(np.random.PCG64(seed))
    transitions = []
    expected_steps = len(data.tasks) + data.num_machines
    terminal = None
    for _ in range(expected_steps):
        if observation.status != 'ACTIVE':
            raise EpisodeInvariantError('A nonterminal policy trajectory must remain ACTIVE')
        encoded = encode_construction_observation(observation)
        features = policy_features(encoded)
        probabilities = tuple(actor.probabilities(encoded))
        if (len(probabilities) != ACTION_COUNT
                or any(not isinstance(value, (float, np.floating)) or not math.isfinite(value) or value < 0
                       for value in probabilities)
                or not math.isclose(math.fsum(probabilities), 1.0, rel_tol=1e-12, abs_tol=1e-12)
                or any(value != 0 for value, legal in zip(probabilities, encoded.action_mask) if not legal)):
            raise EpisodeInvariantError('Actor probabilities violate the exact action mask')
        action = actor.select_action(encoded, rng=rng, deterministic=deterministic)
        if type(action) is not int or not 0 <= action < ACTION_COUNT or not encoded.action_mask[action]:
            raise EpisodeInvariantError('Actor selected an illegal action; no mask repair is permitted')
        budget()
        terminal = env.step(action)
        if not math.isfinite(terminal.reward):
            raise EpisodeInvariantError('Environment returned a nonfinite reward')
        transitions.append(dict(action=action, action_mask=encoded.action_mask,
                                probabilities=probabilities, reward=terminal.reward, features=features))
        observation = terminal.observation
        if terminal.truncated or observation.status in ('TRUNCATED', 'FAILED'):
            raise EpisodeInvariantError('A truncated or failed trajectory has no accepted episode')
        if terminal.terminated:
            break
    if (terminal is None or not terminal.terminated or terminal.truncated
            or observation.status != 'TERMINATED' or len(transitions) != expected_steps
            or observation.steps != expected_steps or terminal.result is None):
        raise EpisodeInvariantError('Policy trajectory did not complete all n+m transitions')
    result = env.get_result()
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    if not accepted:
        raise EpisodeInvariantError(f'Original G1 rejected policy episode: {issues}')
    tardiness = calculate_total_tardiness(data, result)
    rewards = tuple(item['reward'] for item in transitions)
    total_reward = math.fsum(rewards)
    if result.total_tardiness != tardiness:
        raise EpisodeInvariantError('Independent tardiness differs from the episode result')
    if not math.isclose(total_reward, -tardiness / REWARD_SCALE, rel_tol=1e-12, abs_tol=1e-12):
        raise EpisodeInvariantError('Policy return differs from original -tardiness/100 reward')
    budget()
    # Exact undiscounted reward-to-go; no shaping, baseline, entropy or replay.
    samples = tuple(PolicySample(item['features'], item['action_mask'], item['action'], math.fsum(rewards[index:]))
                    for index, item in enumerate(transitions))
    return PolicyEpisode(tuple(item['action'] for item in transitions), rewards, total_reward,
                         result, samples, tuple(transitions))


def train_policy(
    training_instances: tuple, validation_instances: tuple, *, mode: str, seed: int,
    episodes: int = 64, validation_every: int = 16, learning_rate: float = .01,
    hidden_size: int = 16, check_budget: Callable[[], None] | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """Train at most 64 full on-policy episodes; pick the earliest best validation.

    Initial validation is episode zero and may remain the selected untrained
    model. Training data rotate in input order; validation never supplies a
    gradient. Every returned/checkpoint state is a detached parameter copy.
    """
    _integer(seed, 'seed', 0, 2**32 - 1)
    _integer(episodes, 'episodes', 1, 64)
    _integer(validation_every, 'validation_every', 1)
    _integer(hidden_size, 'hidden_size', 1, 16)
    if (type(mode) is not str or mode not in ('fixed', 'joint')
            or type(learning_rate) not in (float, int) or not math.isfinite(learning_rate) or not 0 < learning_rate <= 1):
        raise ValueError('Expected supported mode and finite learning_rate in (0, 1]')
    _callback(on_progress, 'on_progress')
    budget = _deadline_budget(check_budget)
    for split, maximum in ((training_instances, 16), (validation_instances, 4)):
        if (type(split) is not tuple or not 1 <= len(split) <= maximum
                or any(not isinstance(data, ParallelMaintenanceInstance) for data in split)):
            raise ValueError('Training/validation must be nonempty bounded tuples of typed instances')
        for data in split:
            ParallelMaintenanceEnv(data, mode=mode)  # Validate complete uncropped domain before learning.
    training_ids = tuple(base_instance_identity(data) for data in training_instances)
    validation_ids = tuple(base_instance_identity(data) for data in validation_instances)
    if set(training_ids) & set(validation_ids):
        raise ValueError('Training and validation base task identities must be disjoint; overlap rejected')
    budget()
    actor = MaskedMLP(seed=seed, hidden_size=hidden_size)
    initial_state = actor.state_dict()
    selected_state = actor.state_dict()
    selected_episode, best_mean = 0, math.inf
    logs, validation_history = [], []
    training_steps = 0

    def validate(episode_number):
        nonlocal selected_state, selected_episode, best_mean
        budget()
        rows = []
        for index, data in enumerate(validation_instances):
            budget()
            # Greedy evaluation has no RNG effects; retain a reproducible local seed as evidence.
            validation_seed = (seed + index) % 2**32
            completed = run_policy_episode(data, mode=mode, actor=actor, seed=validation_seed,
                                           deterministic=True, check_budget=budget)
            rows.append(dict(validation_index=index, instance_identity=validation_ids[index], seed=validation_seed,
                             actions=completed.actions, rewards=completed.rewards,
                             total_tardiness=completed.result.total_tardiness, total_reward=completed.total_reward))
        mean = math.fsum(row['total_tardiness'] for row in rows) / len(rows)
        current_state = actor.state_dict()
        if mean < best_mean:  # Strict improvement preserves the earliest checkpoint on ties.
            best_mean, selected_episode = mean, episode_number
            selected_state = actor.state_dict()
        history = dict(episode=episode_number, training_steps=training_steps, validation_mean_tardiness=mean,
                       validation_rows=rows, selected_episode=selected_episode)
        validation_history.append(deepcopy(history))
        if on_progress is not None:
            # These validated rollouts and selection already completed. Persist
            # them before a boundary deadline can stop subsequent work.
            on_progress(dict(kind='validation', **deepcopy(history), current_state=current_state,
                             selected_state={name: value.copy() for name, value in selected_state.items()}))
        budget()

    validate(0)
    for episode_number in range(1, episodes + 1):
        budget()
        index = (episode_number - 1) % len(training_instances)
        episode_seed = (seed + episode_number) % 2**32
        completed = run_policy_episode(training_instances[index], mode=mode, actor=actor, seed=episode_seed,
                                       check_budget=budget)
        budget()
        before = actor.state_dict()
        update = actor.reinforce_update(completed.samples, learning_rate=float(learning_rate), max_grad_norm=1.0)
        after = actor.state_dict()
        changed = any(not np.array_equal(before[name], after[name]) for name in before)
        if type(update) is not dict or update.get('changed') is not changed:
            raise EpisodeInvariantError('Optimizer parameter-change evidence disagrees with actual parameters')
        training_steps += len(completed.actions)
        log = dict(episode=episode_number, training_index=index, instance_identity=training_ids[index], seed=episode_seed,
                   actions=completed.actions, rewards=completed.rewards, total_tardiness=completed.result.total_tardiness,
                   total_reward=completed.total_reward, update=deepcopy(update))
        logs.append(log)
        if on_progress is not None:
            on_progress(dict(kind='episode', episode=episode_number, training_steps=training_steps, log=deepcopy(log)))
        if episode_number % validation_every == 0 or episode_number == episodes:
            validate(episode_number)
    budget()
    return dict(initial_state=initial_state, final_state=actor.state_dict(),
                selected_state={name: value.copy() for name, value in selected_state.items()},
                logs=logs, validation_history=validation_history, selected_episode=selected_episode,
                episodes_completed=episodes, training_steps=training_steps)
