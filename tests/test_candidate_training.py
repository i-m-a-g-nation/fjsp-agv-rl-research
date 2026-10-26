"""Candidate training uses checked original episodes and validation-only selection."""
import importlib
import importlib.util
from pathlib import Path
import random

import numpy as np
import pytest

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation import policy_training as original


def _api():
    try:
        return importlib.import_module('src.graduation.candidate_training')
    except ModuleNotFoundError:
        pytest.fail('The controlled candidate trainer has not been implemented')


def _data(due=(0, 1), *, fixed_start=0):
    return ParallelMaintenanceInstance(tuple(ProductionTask(j, 2, d) for j, d in enumerate(due)), 1,
        (MaintenanceRequirement(0, 2, 0, 6, fixed_start),))


def _same(a, b):
    return all(np.array_equal(a[key], b[key]) for key in a)


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
def test_reproducible_training_retains_original_checked_reward_and_detached_progress(mode):
    m, events = _api(), []
    py, legacy = random.getstate(), np.random.get_state()
    first = m.train_shared_policy((_data(), _data((2, 3))), (_data((100, 101)),),
        mode=mode, seed=17, episodes=3, validation_every=2, on_progress=events.append)
    second = m.train_shared_policy((_data(), _data((2, 3))), (_data((100, 101)),),
        mode=mode, seed=17, episodes=3, validation_every=2)
    assert set(first) == {'initial_state', 'final_state', 'selected_state', 'logs', 'validation_history',
                          'selected_episode', 'episodes_completed', 'training_steps'}
    assert first['episodes_completed'] == 3 and first['training_steps'] == 9
    assert first['logs'] == second['logs'] and _same(first['final_state'], second['final_state'])
    assert [row['training_index'] for row in first['logs']] == [0, 1, 0]
    assert [row['seed'] for row in first['logs']] == [18, 19, 20]
    assert [row['episode'] for row in first['validation_history']] == [0, 2, 3]
    assert first['selected_episode'] == 0 and _same(first['selected_state'], first['initial_state'])
    assert not _same(first['final_state'], first['initial_state'])
    for row in first['logs']:
        assert row['total_reward'] == pytest.approx(-row['total_tardiness']/100)
        assert 'return_baseline' not in row
    assert [e['kind'] for e in events] == ['validation', 'episode', 'episode', 'validation', 'episode', 'validation']
    assert all({'current_state', 'selected_state'} <= set(e) for e in events if e['kind'] == 'validation')
    before = first['selected_state']['w1'].copy()
    events[0]['selected_state']['w1'][:] = 999
    events[0]['current_state']['w1'][:] = 999
    first['final_state']['w1'][:] = 999
    assert np.array_equal(first['selected_state']['w1'], before)
    assert random.getstate() == py
    after = np.random.get_state()
    assert legacy[0] == after[0] and np.array_equal(legacy[1], after[1]) and legacy[2:] == after[2:]


def test_trainer_accepts_separately_loaded_exact_template_class_and_uses_it(tmp_path):
    m = _api()
    from src.graduation.candidate_templates import shared_scorer
    target = tmp_path/'shared_scorer.py'
    target.write_bytes(Path(shared_scorer.__file__).read_bytes())
    spec = importlib.util.spec_from_file_location('batch_candidate', target)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    actors = []

    class Tracked(loaded.SharedScorer):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            actors.append(self)

    result = m.train_shared_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17,
                                  episodes=1, actor_class=Tracked)
    assert len(actors) == 1 and _same(result['final_state'], actors[0].state_dict())


def test_earliest_strictly_improved_validation_checkpoint_wins_over_last_state():
    m, events = _api(), []
    from src.graduation.candidate_templates.shared_scorer import SharedScorer

    class Controlled(SharedScorer):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.updates = 0

        def select_action(self, encoded, *, rng, deterministic=False):
            if not deterministic:
                return super().select_action(encoded, rng=rng)
            priority = (0, 4, 96) if self.updates == 1 else (96, 0, 4)
            return next(action for action in priority if encoded.action_mask[action])

        def reinforce_update(self, samples, **kwargs):
            update = super().reinforce_update(samples, **kwargs)
            self.updates += 1
            return update

    result = m.train_shared_policy((_data(),), (_data((0, 0)),), mode='joint', seed=17,
        episodes=2, validation_every=1, actor_class=Controlled, on_progress=events.append)
    assert [row['validation_mean_tardiness'] for row in result['validation_history']] == [10., 6., 10.]
    assert result['selected_episode'] == 1
    middle = next(e for e in events if e['kind'] == 'validation' and e['episode'] == 1)
    assert _same(result['selected_state'], middle['current_state'])
    assert not _same(result['selected_state'], result['initial_state'])
    assert not _same(result['selected_state'], result['final_state'])


@pytest.mark.parametrize('fault', ['overlap', 'condition_overlap', 'empty', 'list', 'too_many', 'untyped'])
def test_training_rejects_invalid_splits_before_progress(fault):
    m, events = _api(), []
    train, validation = (_data(),), (_data((100, 101)),)
    if fault == 'overlap': validation = train
    if fault == 'condition_overlap': validation = (_data(fixed_start=2),)
    if fault == 'empty': train = ()
    if fault == 'list': train = list(train)
    if fault == 'too_many': validation = tuple(_data((100+i, 101+i)) for i in range(5))
    if fault == 'untyped': train = (object(),)
    with pytest.raises(ValueError):
        m.train_shared_policy(train, validation, mode='joint', seed=17, episodes=1, on_progress=events.append)
    assert events == []


@pytest.mark.parametrize('key,value', [('episodes', 0), ('episodes', 65), ('episodes', True),
    ('validation_every', 0), ('validation_every', True), ('seed', -1), ('seed', True),
    ('mode', 'unsupported'), ('check_budget', 1), ('on_progress', 1), ('actor_class', object),
    ('actor_class', original.MaskedMLP)])
def test_training_rejects_invalid_bounded_configuration(key, value):
    kwargs = dict(mode='joint', seed=17, episodes=1)
    kwargs[key] = value
    with pytest.raises(ValueError):
        _api().train_shared_policy((_data(),), (_data((100, 101)),), **kwargs)


def test_original_checker_rejection_propagates_without_training(monkeypatch):
    events = []
    monkeypatch.setattr(original, 'check_parallel_maintenance_feasibility', lambda *a, **k: (False, ['refused']))
    with pytest.raises(original.EpisodeInvariantError, match='G1'):
        _api().train_shared_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17,
                                  episodes=1, on_progress=events.append)
    assert events == []


@pytest.mark.parametrize('partial', [False, True])
def test_budget_rejects_partial_or_expired_complete_episode_before_update(monkeypatch, partial):
    m, events, actors = _api(), [], []
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    real_episode, real_step = m.run_policy_episode, original.ParallelMaintenanceEnv.step
    finished, steps = [False], [0]

    class Tracked(SharedScorer):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            actors.append(self)

    def episode(*args, **kwargs):
        if partial and not kwargs.get('deterministic', False):
            def stop():
                if steps[0] >= 1: raise TimeoutError('partial episode')
            kwargs['check_budget'] = stop
        result = real_episode(*args, **kwargs)
        if not kwargs.get('deterministic', False): finished[0] = True
        return result

    def step(self, action):
        result = real_step(self, action)
        steps[0] += 1
        return result

    def progress(event):
        events.append(event)
        if event['kind'] == 'validation': steps[0] = 0

    def budget():
        if finished[0]: raise TimeoutError('expired before update')

    monkeypatch.setattr(m, 'run_policy_episode', episode)
    monkeypatch.setattr(original.ParallelMaintenanceEnv, 'step', step)
    with pytest.raises(TimeoutError, match='partial|before update'):
        m.train_shared_policy((_data(),), (_data((100, 101)),), mode='joint', seed=17, episodes=1,
                              actor_class=Tracked, check_budget=budget, on_progress=progress)
    assert [e['kind'] for e in events] == ['validation']
    assert _same(actors[0].state_dict(), events[0]['current_state'])
