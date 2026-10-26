"""Bounded, on-policy training must retain the original acceptance contract."""

from dataclasses import FrozenInstanceError, replace
import random

import numpy as np
import pytest

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.feasibility import check_parallel_maintenance_feasibility


def _data(due_dates=(0, 1), *, machines=1, fixed_start=0):
    return ParallelMaintenanceInstance(
        tuple(ProductionTask(j, 2, due) for j, due in enumerate(due_dates)), machines,
        tuple(MaintenanceRequirement(i, 2, 0, 6, fixed_start) for i in range(machines)),
    )


def _states_equal(first, second):
    return all(np.array_equal(first[key], second[key]) for key in first)


def _apis():
    from src.graduation import policy_training as training
    from src.graduation.neural_policy import MaskedMLP
    return training, MaskedMLP


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
def test_episode_is_legal_complete_and_contains_exact_gamma_one_returns_without_learning(mode):
    training, actor_type = _apis()
    data = _data()
    actor = actor_type(seed=17)
    before = actor.state_dict()
    episode = training.run_policy_episode(data, mode=mode, actor=actor, seed=29)
    assert check_parallel_maintenance_feasibility(episode.result, data, mode=mode) == (True, [])
    assert len(episode.actions) == len(episode.rewards) == len(episode.samples) == 3
    assert len(episode.transitions) == 3
    assert episode.total_reward == pytest.approx(-episode.result.total_tardiness / 100)
    for index, (action, sample, transition) in enumerate(zip(episode.actions, episode.samples, episode.transitions)):
        assert transition['action'] == sample.action == action
        assert transition['action_mask'][action] is True
        assert len(transition['probabilities']) == 100
        assert all(probability == 0 for probability, legal in zip(transition['probabilities'], transition['action_mask']) if not legal)
        assert sum(transition['probabilities']) == pytest.approx(1)
        assert transition['features'] == sample.features
        assert transition['reward'] == episode.rewards[index]
        assert sample.return_value == pytest.approx(sum(episode.rewards[index:]))
    assert _states_equal(before, actor.state_dict())
    with pytest.raises(FrozenInstanceError):
        episode.total_reward = 1.0


def test_local_episode_and_training_rng_leave_python_and_numpy_global_streams_untouched():
    training, actor_type = _apis()
    python_before = random.getstate()
    numpy_before = np.random.get_state()
    data = _data()
    first = training.run_policy_episode(data, mode='joint', actor=actor_type(seed=3), seed=7)
    second = training.run_policy_episode(data, mode='joint', actor=actor_type(seed=3), seed=7)
    trained = training.train_policy((data,), (_data((4, 5)),), mode='joint', seed=17, episodes=2, validation_every=1)
    assert first.actions == second.actions
    assert first.transitions == second.transitions
    assert trained['training_steps'] == 6
    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_before[0] == numpy_after[0] and np.array_equal(numpy_before[1], numpy_after[1])
    assert numpy_before[2:] == numpy_after[2:]


def test_illegal_actor_action_is_rejected_without_mask_repair():
    training, actor_type = _apis()

    class IllegalActor(actor_type):
        def select_action(self, encoded, **kwargs):
            return 99  # Padded maintenance machine, even though legal choices exist.

    with pytest.raises((ValueError, training.EpisodeInvariantError)):
        training.run_policy_episode(_data(), mode='joint', actor=IllegalActor(seed=3), seed=7)


def test_independent_acceptance_refusal_prevents_an_accepted_episode(monkeypatch):
    training, actor_type = _apis()
    monkeypatch.setattr(training, 'check_parallel_maintenance_feasibility', lambda *a, **k: (False, ['refused']))
    with pytest.raises(training.EpisodeInvariantError, match='G1'):
        training.run_policy_episode(_data(), mode='joint', actor=actor_type(seed=3), seed=7)


def test_independent_tardiness_and_reward_checks_reject_a_corrupted_metric(monkeypatch):
    training, actor_type = _apis()
    monkeypatch.setattr(training, 'calculate_total_tardiness', lambda *a: 999)
    with pytest.raises(training.EpisodeInvariantError, match='tardiness|return'):
        training.run_policy_episode(_data(), mode='joint', actor=actor_type(seed=3), seed=7)


@pytest.mark.parametrize('fault', ['reward', 'truncated', 'unterminated'])
def test_corrupted_return_or_nonaccepted_terminal_cannot_become_a_policy_episode(monkeypatch, fault):
    training, actor_type = _apis()
    real_step = training.ParallelMaintenanceEnv.step

    def step(self, action):
        value = real_step(self, action)
        if fault == 'reward':
            return replace(value, reward=value.reward + 1.0)
        if value.terminated:
            return replace(value, terminated=False, truncated=fault == 'truncated', result=None)
        return value

    monkeypatch.setattr(training.ParallelMaintenanceEnv, 'step', step)
    with pytest.raises(training.EpisodeInvariantError):
        training.run_policy_episode(_data(), mode='joint', actor=actor_type(seed=3), seed=7)


def test_budget_mid_rollout_exposes_no_partial_result_or_parameter_update():
    training, actor_type = _apis()
    actor = actor_type(seed=17)
    before = actor.state_dict()
    calls = 0

    def budget():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TimeoutError('test budget')

    with pytest.raises(TimeoutError, match='test budget'):
        training.run_policy_episode(_data(), mode='joint', actor=actor, seed=29, check_budget=budget)
    assert _states_equal(before, actor.state_dict())


def test_base_identity_prevents_task_leakage_across_machine_or_maintenance_variations():
    training, _ = _apis()
    original = _data()
    changed_conditions = _data(machines=2, fixed_start=2)
    assert training.base_instance_identity(original) == training.base_instance_identity(changed_conditions)
    assert training.base_instance_identity(original) != training.base_instance_identity(_data((0, 2)))
    with pytest.raises(ValueError, match='overlap|disjoint|identity'):
        training.train_policy((original,), (changed_conditions,), mode='joint', seed=17, episodes=1)


def test_training_updates_once_after_each_complete_episode_and_round_robins(monkeypatch):
    training, actor_type = _apis()
    timeline = []
    real_episode = training.run_policy_episode
    real_update = actor_type.reinforce_update

    def episode(*args, **kwargs):
        completed = real_episode(*args, **kwargs)
        if not kwargs.get('deterministic', False):
            timeline.append(('complete', completed.samples))
        return completed

    def update(self, samples, **kwargs):
        assert timeline[-1] == ('complete', samples)
        result = real_update(self, samples, **kwargs)
        timeline.append(('update', samples))
        return result

    monkeypatch.setattr(training, 'run_policy_episode', episode)
    monkeypatch.setattr(actor_type, 'reinforce_update', update)
    result = training.train_policy((_data(), _data((1, 2))), (_data((4, 5)),), mode='joint', seed=17,
                                   episodes=3, validation_every=2)
    assert [kind for kind, _ in timeline] == ['complete', 'update'] * 3
    assert [log['training_index'] for log in result['logs']] == [0, 1, 0]
    assert result['episodes_completed'] == 3 and result['training_steps'] == 9
    assert not _states_equal(result['initial_state'], result['final_state'])
    assert all(log['update']['changed'] for log in result['logs'])
    assert all(np.isfinite(value).all() for state in (result['initial_state'], result['final_state'], result['selected_state']) for value in state.values())
    assert set(result) == {'initial_state', 'final_state', 'selected_state', 'logs', 'validation_history',
                           'selected_episode', 'episodes_completed', 'training_steps'}
    repeated = training.train_policy((_data(), _data((1, 2))), (_data((4, 5)),), mode='joint', seed=17,
                                     episodes=3, validation_every=2)
    assert _states_equal(result['final_state'], repeated['final_state'])
    assert result['logs'] == repeated['logs']


def test_zero_tardiness_validation_ties_keep_initial_checkpoint_and_progress_snapshots_are_detached():
    training, _ = _apis()
    events = []
    result = training.train_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17,
                                   episodes=3, validation_every=2, on_progress=events.append)
    assert [row['episode'] for row in result['validation_history']] == [0, 2, 3]
    assert all(row['validation_mean_tardiness'] == 0 for row in result['validation_history'])
    assert result['selected_episode'] == 0
    assert _states_equal(result['initial_state'], result['selected_state'])
    assert not _states_equal(result['initial_state'], result['final_state'])
    assert [event['kind'] for event in events] == ['validation', 'episode', 'episode', 'validation', 'episode', 'validation']
    validation = events[0]
    assert set(validation) == {'kind', 'episode', 'training_steps', 'validation_mean_tardiness', 'validation_rows',
                               'selected_episode', 'current_state', 'selected_state'}
    assert validation['episode'] == validation['selected_episode'] == validation['training_steps'] == 0
    assert len(validation['validation_rows']) == 1
    assert [event['training_steps'] for event in events if event['kind'] == 'episode'] == [3, 6, 9]
    snapshot = result['selected_state']['w1'].copy()
    validation['selected_state']['w1'][:] = 999
    validation['current_state']['w1'][:] = 999
    result['final_state']['w1'][:] = 888
    assert np.array_equal(result['selected_state']['w1'], snapshot)
    assert np.array_equal(result['initial_state']['w1'], snapshot)


def test_validation_selects_an_earlier_improved_checkpoint_instead_of_last_training_state(monkeypatch):
    training, actor_type = _apis()
    events = []

    class ControlledGreedyActor(actor_type):
        """Literal legal validation plans isolate selection from noisy learning gains."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.updates = 0

        def select_action(self, encoded, *, rng, deterministic=False):
            if not deterministic:
                return super().select_action(encoded, rng=rng, deterministic=False)
            # All p=2,d=0: maintenance first gives T=4+6=10;
            # production first gives T=2+4=6, both through the real environment.
            priority = (0, 4, 96) if self.updates == 1 else (96, 0, 4)
            return next(action for action in priority if encoded.action_mask[action])

        def reinforce_update(self, samples, **kwargs):
            update = super().reinforce_update(samples, **kwargs)
            self.updates += 1
            return update

    monkeypatch.setattr(training, 'MaskedMLP', ControlledGreedyActor)
    result = training.train_policy((_data(),), (_data((0, 0)),), mode='joint', seed=17,
                                   episodes=2, validation_every=1, on_progress=events.append)
    assert [row['validation_mean_tardiness'] for row in result['validation_history']] == [10.0, 6.0, 10.0]
    assert result['selected_episode'] == 1
    selected_event = next(event for event in events if event['kind'] == 'validation' and event['episode'] == 1)
    assert _states_equal(result['selected_state'], selected_event['current_state'])
    assert not _states_equal(result['selected_state'], result['initial_state'])
    assert not _states_equal(result['selected_state'], result['final_state'])


def test_budget_interrupt_during_training_never_learns_from_partial_episode(monkeypatch):
    training, actor_type = _apis()
    real_episode = training.run_policy_episode
    real_step = training.ParallelMaintenanceEnv.step
    steps = 0
    completed_events = []
    actors = []

    class TrackedActor(actor_type):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            actors.append(self)

    def episode(*args, **kwargs):
        if not kwargs.get('deterministic', False):
            def stop_after_first():
                if steps >= 1:
                    raise TimeoutError('training interrupted')
            kwargs['check_budget'] = stop_after_first
        return real_episode(*args, **kwargs)

    def step(self, action):
        nonlocal steps
        value = real_step(self, action)
        steps += 1
        return value

    # Initial validation completes, then the training-only counter begins.
    def progress(event):
        nonlocal steps
        completed_events.append(event)
        if event['kind'] == 'validation':
            steps = 0

    monkeypatch.setattr(training, 'MaskedMLP', TrackedActor)
    monkeypatch.setattr(training, 'run_policy_episode', episode)
    monkeypatch.setattr(training.ParallelMaintenanceEnv, 'step', step)
    with pytest.raises(TimeoutError, match='training interrupted'):
        training.train_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17,
                              episodes=2, on_progress=progress)
    assert [event['kind'] for event in completed_events] == ['validation']
    assert _states_equal(actors[0].state_dict(), completed_events[0]['current_state'])


def test_budget_is_checked_again_between_completed_rollout_and_update(monkeypatch):
    training, actor_type = _apis()
    real_episode = training.run_policy_episode
    training_finished = False
    actors, events = [], []

    class TrackedActor(actor_type):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            actors.append(self)

    def episode(*args, **kwargs):
        nonlocal training_finished
        completed = real_episode(*args, **kwargs)
        if not kwargs.get('deterministic', False):
            training_finished = True
        return completed

    def budget():
        if training_finished:
            raise TimeoutError('expired before update')

    monkeypatch.setattr(training, 'MaskedMLP', TrackedActor)
    monkeypatch.setattr(training, 'run_policy_episode', episode)
    with pytest.raises(TimeoutError, match='expired before update'):
        training.train_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17,
                              episodes=1, check_budget=budget, on_progress=events.append)
    assert len(events) == 1 and events[0]['kind'] == 'validation'
    assert _states_equal(actors[0].state_dict(), events[0]['current_state'])


def test_internal_deadline_applies_even_without_a_caller_budget(monkeypatch):
    training, _ = _apis()
    clock = [0.0]
    monkeypatch.setattr(training.time, 'monotonic', lambda: clock[0])

    def progress(event):
        if event['kind'] == 'episode':
            clock[0] = 121.0

    with pytest.raises(TimeoutError, match='120|budget|deadline'):
        training.train_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17,
                              episodes=1, validation_every=1, on_progress=progress)


def test_unsupported_learning_rate_fails_before_any_validation_or_rollout():
    training, _ = _apis()
    events = []
    with pytest.raises(ValueError):
        training.train_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17,
                              episodes=1, learning_rate=1.1, on_progress=events.append)
    assert events == []


def test_completed_validation_is_emitted_before_boundary_deadline(monkeypatch):
    training, actor_type = _apis()
    snapshots, expired, events = [0], [False], []
    class DeadlineActor(actor_type):
        def state_dict(self):
            state = super().state_dict()
            snapshots[0] += 1
            if snapshots[0] == 4:  # initial/current/selected copies have completed
                expired[0] = True
            return state
    def budget():
        if expired[0]: raise TimeoutError('expired after validation selection')
    monkeypatch.setattr(training, 'MaskedMLP', DeadlineActor)
    with pytest.raises(TimeoutError, match='after validation selection'):
        training.train_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17,
                              episodes=1, check_budget=budget, on_progress=events.append)
    assert snapshots[0] == 4 and len(events) == 1
    assert events[0]['kind'] == 'validation' and events[0]['episode'] == 0
    assert events[0]['selected_episode'] == 0
    assert _states_equal(events[0]['current_state'], events[0]['selected_state'])


@pytest.mark.parametrize('keyword,value', [
    ('episodes', 0), ('episodes', 65), ('episodes', True), ('episodes', 1.5),
    ('validation_every', 0), ('validation_every', True), ('seed', True), ('seed', -1), ('seed', 2**32),
    ('hidden_size', 0), ('hidden_size', 17), ('learning_rate', 0), ('learning_rate', float('nan')),
    ('mode', 'unsupported'),
])
def test_training_rejects_unbounded_or_malformed_configuration(keyword, value):
    training, _ = _apis()
    kwargs = dict(mode='joint', seed=17, episodes=1)
    kwargs[keyword] = value
    with pytest.raises(ValueError):
        training.train_policy((_data(),), (_data((100, 101)),), **kwargs)


@pytest.mark.parametrize('split', ['empty_train', 'empty_validation', 'list_train', 'too_many_train', 'too_many_validation', 'untyped'])
def test_training_rejects_unbounded_or_untyped_splits(split):
    training, _ = _apis()
    train, validation = (_data(),), (_data((100, 101)),)
    if split == 'empty_train': train = ()
    if split == 'empty_validation': validation = ()
    if split == 'list_train': train = list(train)
    if split == 'too_many_train': train = tuple(_data((j, j + 1)) for j in range(17))
    if split == 'too_many_validation': validation = tuple(_data((100 + j, 101 + j)) for j in range(5))
    if split == 'untyped': train = (object(),)
    with pytest.raises(ValueError):
        training.train_policy(train, validation, mode='joint', seed=17, episodes=1)
