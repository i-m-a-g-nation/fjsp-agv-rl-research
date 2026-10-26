"""Bounded shared-scorer REINFORCE using unchanged checked R1 rollouts.

Reward remains -total_tardiness/100 with gamma=1 and no return baseline.
Only validation selects the earliest strictly best checkpoint. The optional
actor_class allows the controller's hash-verified batch template to execute;
the controller owns file provenance, while this boundary checks actor/schema.
"""
from copy import deepcopy
import math
from typing import Callable

import numpy as np

from src.graduation.candidate_templates.shared_scorer import SharedScorer
from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.neural_policy import MaskedMLP
from src.graduation.policy_training import (
    _callback, _deadline_budget, _integer, base_instance_identity, run_policy_episode,
)
from src.graduation.rl_environment import EpisodeInvariantError, ParallelMaintenanceEnv


def train_shared_policy(
    training_instances: tuple, validation_instances: tuple, *, mode: str, seed: int,
    episodes: int = 64, validation_every: int = 16,
    check_budget: Callable[[], None] | None = None,
    on_progress: Callable[[dict], None] | None = None, actor_class=None,
) -> dict:
    """Train full original episodes and emit original-compatible progress records."""
    _integer(seed, 'seed', 0, 2**32-1)
    _integer(episodes, 'episodes', 1, 64)
    _integer(validation_every, 'validation_every', 1)
    if type(mode) is not str or mode not in ('fixed', 'joint'):
        raise ValueError('Expected supported fixed/joint mode')
    _callback(on_progress, 'on_progress')
    budget = _deadline_budget(check_budget)
    actor_class = SharedScorer if actor_class is None else actor_class
    if (not isinstance(actor_class, type) or not issubclass(actor_class, MaskedMLP)
            or getattr(actor_class, 'policy_kind', None) != 'shared_scorer_v1'):
        raise ValueError('Expected a shared_scorer_v1 MaskedMLP subclass')
    for split, maximum in ((training_instances, 16), (validation_instances, 4)):
        if (type(split) is not tuple or not 1 <= len(split) <= maximum
                or any(not isinstance(data, ParallelMaintenanceInstance) for data in split)):
            raise ValueError('Training/validation must be nonempty bounded tuples of typed instances')
        for data in split:
            ParallelMaintenanceEnv(data, mode=mode)
    training_ids = tuple(base_instance_identity(data) for data in training_instances)
    validation_ids = tuple(base_instance_identity(data) for data in validation_instances)
    if set(training_ids) & set(validation_ids):
        raise ValueError('Training and validation base task identities must be disjoint; overlap rejected')
    budget()
    actor = actor_class(seed=seed, hidden_size=16)
    initial_state = actor.state_dict()
    SharedScorer.from_state(initial_state)  # Reject an old/malformed schema before any rollout.
    selected_state = {name: value.copy() for name, value in initial_state.items()}
    selected_episode, best_mean, training_steps = 0, math.inf, 0
    logs, validation_history = [], []

    def validate(episode_number):
        nonlocal selected_state, selected_episode, best_mean
        budget()
        rows = []
        for index, data in enumerate(validation_instances):
            budget()
            validation_seed = (seed+index) % 2**32
            completed = run_policy_episode(data, mode=mode, actor=actor, seed=validation_seed,
                                           deterministic=True, check_budget=budget)
            rows.append(dict(validation_index=index, instance_identity=validation_ids[index], seed=validation_seed,
                actions=completed.actions, rewards=completed.rewards,
                total_tardiness=completed.result.total_tardiness, total_reward=completed.total_reward))
        mean = math.fsum(row['total_tardiness'] for row in rows)/len(rows)
        current_state = actor.state_dict()
        if mean < best_mean:
            best_mean, selected_episode = mean, episode_number
            selected_state = actor.state_dict()
        history = dict(episode=episode_number, training_steps=training_steps,
            validation_mean_tardiness=mean, validation_rows=rows, selected_episode=selected_episode)
        validation_history.append(deepcopy(history))
        if on_progress is not None:
            on_progress(dict(kind='validation', **deepcopy(history), current_state=current_state,
                selected_state={name: value.copy() for name, value in selected_state.items()}))
        budget()

    validate(0)
    for episode_number in range(1, episodes+1):
        budget()
        index = (episode_number-1) % len(training_instances)
        episode_seed = (seed+episode_number) % 2**32
        completed = run_policy_episode(training_instances[index], mode=mode, actor=actor,
            seed=episode_seed, check_budget=budget)
        budget()  # A completed rollout cannot authorize an update after expiry.
        before = actor.state_dict()
        update = actor.reinforce_update(completed.samples, learning_rate=.01, max_grad_norm=1.)
        after = actor.state_dict()
        changed = any(not np.array_equal(before[name], after[name]) for name in before)
        if type(update) is not dict or update.get('changed') is not changed:
            raise EpisodeInvariantError('Optimizer parameter-change evidence disagrees with actual parameters')
        training_steps += len(completed.actions)
        log = dict(episode=episode_number, training_index=index, instance_identity=training_ids[index],
            seed=episode_seed, actions=completed.actions, rewards=completed.rewards,
            total_tardiness=completed.result.total_tardiness, total_reward=completed.total_reward,
            update=deepcopy(update))
        logs.append(log)
        if on_progress is not None:
            on_progress(dict(kind='episode', episode=episode_number, training_steps=training_steps, log=deepcopy(log)))
        if episode_number % validation_every == 0 or episode_number == episodes:
            validate(episode_number)
    budget()
    return dict(initial_state=initial_state, final_state=actor.state_dict(),
        selected_state={name: value.copy() for name, value in selected_state.items()}, logs=logs,
        validation_history=validation_history, selected_episode=selected_episode,
        episodes_completed=episodes, training_steps=training_steps)
