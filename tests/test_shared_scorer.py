"""Shared action scoring preserves masks, gradients and physical relabeling."""
from dataclasses import replace
import importlib
import math
import random

import numpy as np
import pytest

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.neural_policy import MaskedMLP, PolicySample, policy_features
from src.graduation.permutation_diagnostics import _permutation
from src.graduation.policy_training import run_policy_episode
from src.graduation.rl_environment import ParallelMaintenanceEnv
from src.graduation.state_encoding import encode_construction_observation


def _api():
    try:
        return importlib.import_module('src.graduation.candidate_templates.shared_scorer')
    except ModuleNotFoundError:
        pytest.fail('The shared scorer template has not been implemented')


def _data():
    return ParallelMaintenanceInstance(
        (ProductionTask(0, 2, 1), ProductionTask(1, 3, 4), ProductionTask(2, 1, 8)), 2,
        (MaintenanceRequirement(0, 2, 1, 10, 4), MaintenanceRequirement(1, 3, 2, 11, 5)))


def _encoded(mode='joint'):
    return encode_construction_observation(ParallelMaintenanceEnv(_data(), mode=mode).observe())


def _sample(value=1.0):
    encoded = _encoded()
    return PolicySample(policy_features(encoded), encoded.action_mask, 0, value)


def _same(a, b):
    return all(np.array_equal(a[key], b[key]) for key in a)


def test_template_has_detached_finite_fixed_545_parameter_schema_and_original_actor_compatibility():
    m = _api()
    actor = m.SharedScorer(seed=17)
    assert isinstance(actor, MaskedMLP) and actor.hidden_size == 16
    state = actor.state_dict()
    assert {k: v.shape for k, v in state.items()} == {'w1': (32, 16), 'b1': (16,), 'w2': (16,), 'b2': (1,)}
    assert sum(v.size for v in state.values()) == 545
    assert all(v.dtype == np.float64 and np.isfinite(v).all() for v in state.values())
    restored = m.SharedScorer.from_state(state)
    state['w1'][:] = 999
    assert actor.probabilities(_encoded()) == restored.probabilities(_encoded())
    snapshot = restored.state_dict()
    snapshot['b1'][:] = 123
    assert _same(actor.state_dict(), restored.state_dict())


def test_action_features_exclude_padding_and_have_literal_local_pool_and_slack_values():
    m = _api()
    features = m.action_features(policy_features(_encoded()))
    assert features.shape == (100, 32)
    assert features[0, :12] == pytest.approx([2/3, 1/3, 0, 0, 2/3, 1/3, 10/3, 4/3, 0, 1, 1, 0])
    assert features[0, 20:30] == pytest.approx([2/3, 13/9, 0, 0, 5/6, 1/2, 7/2, 3/2, 0, 1])
    assert features[0, 30:] == pytest.approx([-1/3, 8/3])
    assert features[96, :3].tolist() == [0, 0, 0]
    assert features[96, 10:12].tolist() == [0, 1]
    assert features[96, 30:] == pytest.approx([0, 8/3])
    assert m.action_features(policy_features(_encoded('fixed')))[0, 31] == pytest.approx(4/3)


@pytest.mark.parametrize('key', ['w1', 'b1', 'w2', 'b2'])
def test_every_analytic_parameter_derivative_matches_independent_central_difference(key):
    m = _api()
    actor = m.SharedScorer(seed=3)
    state, item, epsilon = actor.state_dict(), _sample(), 1e-6
    logp, gradient = actor.log_probability_gradient(item)
    assert logp == pytest.approx(math.log(actor.probabilities(_encoded())[0]))
    for index in np.ndindex(state[key].shape):
        plus = {k: v.copy() for k, v in state.items()}
        minus = {k: v.copy() for k, v in state.items()}
        plus[key][index] += epsilon
        minus[key][index] -= epsilon
        high = math.log(m.SharedScorer.from_state(plus).probabilities(_encoded())[0])
        low = math.log(m.SharedScorer.from_state(minus).probabilities(_encoded())[0])
        assert gradient[key][index] == pytest.approx((high-low)/(2*epsilon), abs=2e-8, rel=2e-5)
    assert _same(state, actor.state_dict())


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
@pytest.mark.parametrize('name', ['jobs_reverse', 'machines_reverse', 'both_reverse'])
@pytest.mark.parametrize('updated', [False, True])
def test_probability_equivariance_at_every_same_physical_replayed_state(mode, name, updated):
    actor = _api().SharedScorer(seed=17)
    data = _data()
    if updated:
        completed = run_policy_episode(data, mode=mode, actor=actor, seed=29)
        assert actor.reinforce_update(completed.samples)['changed']
    transformed, _, _, action_map = _permutation(data, name)
    original, mapped = ParallelMaintenanceEnv(data, mode=mode), ParallelMaintenanceEnv(transformed, mode=mode)
    for _ in range(len(data.tasks)+data.num_machines):
        a, b = encode_construction_observation(original.observe()), encode_construction_observation(mapped.observe())
        p, q = actor.probabilities(a), actor.probabilities(b)
        assert p == pytest.approx([q[action_map[i]] for i in range(100)], abs=2e-15)
        assert all(p[i] == 0 for i in range(100) if not a.action_mask[i])
        action = int(np.argmax(p))
        original.step(action)
        mapped.step(action_map[action])
    assert original.get_result().total_tardiness == mapped.get_result().total_tardiness


def test_stochastic_selection_is_seeded_and_greedy_selection_uses_distribution_without_global_rng_changes():
    actor = _api().SharedScorer(seed=17)
    before_py, before_np = random.getstate(), np.random.get_state()
    a, b = np.random.default_rng(29), np.random.default_rng(29)
    first = [actor.select_action(_encoded(), rng=a) for _ in range(60)]
    assert first == [actor.select_action(_encoded(), rng=b) for _ in range(60)]
    assert actor.select_action(_encoded(), rng=a, deterministic=True) == int(np.argmax(actor.probabilities(_encoded())))
    assert random.getstate() == before_py
    after_np = np.random.get_state()
    assert before_np[0] == after_np[0] and np.array_equal(before_np[1], after_np[1]) and before_np[2:] == after_np[2:]
    with pytest.raises(ValueError):
        actor.probabilities(replace(_encoded(), status='TERMINATED', action_mask=(False,)*100))


@pytest.mark.parametrize('value,sign', [(1.0, 1), (-1.0, -1)])
def test_reinforce_update_sign_clipping_and_zero_gradient_for_single_legal_action(value, sign):
    actor = _api().SharedScorer(seed=17)
    before = actor.probabilities(_encoded())[0]
    result = actor.reinforce_update((_sample(value),), learning_rate=.001, max_grad_norm=.1)
    assert sign*(actor.probabilities(_encoded())[0]-before) > 0
    assert result['changed'] and result['samples'] == 1
    assert 0 < result['applied_gradient_norm'] <= .1+1e-12
    item = replace(_sample(-5.), action_mask=tuple(i == 0 for i in range(100)))
    state = actor.state_dict()
    result = actor.reinforce_update((item,))
    assert not result['changed'] and result['gradient_norm'] == 0
    assert _same(state, actor.state_dict())


@pytest.mark.parametrize('fault', ['keys', 'old_schema', 'float32', 'nan', 'shape', 'seed', 'hidden'])
def test_bad_checkpoint_or_configuration_is_rejected(fault):
    m = _api()
    state = m.SharedScorer(seed=17).state_dict()
    if fault == 'keys': state['extra'] = np.zeros(1)
    if fault == 'old_schema': state = MaskedMLP(seed=17).state_dict()
    if fault == 'float32': state['w1'] = state['w1'].astype(np.float32)
    if fault == 'nan': state['b1'][0] = np.nan
    if fault == 'shape': state['w2'] = np.zeros((16, 1))
    with pytest.raises(ValueError):
        if fault == 'seed': m.SharedScorer(seed=True)
        elif fault == 'hidden': m.SharedScorer(seed=17, hidden_size=15)
        else: m.SharedScorer.from_state(state)


@pytest.mark.parametrize('fault', ['features', 'mask', 'action', 'return', 'overflow', 'lr', 'norm', 'samples'])
def test_invalid_or_overflowing_update_is_atomic(fault):
    actor, item, kwargs = _api().SharedScorer(seed=17), _sample(), {}
    if fault == 'features': object.__setattr__(item, 'features', (0.,)*371)
    if fault == 'mask': object.__setattr__(item, 'action_mask', (False,)*100)
    if fault == 'action': object.__setattr__(item, 'action', 99)
    if fault == 'return': object.__setattr__(item, 'return_value', float('nan'))
    if fault == 'overflow': object.__setattr__(item, 'return_value', 1e308)
    if fault == 'lr': kwargs['learning_rate'] = float('nan')
    if fault == 'norm': kwargs['max_grad_norm'] = 0.
    state = actor.state_dict()
    with pytest.raises(ValueError):
        actor.reinforce_update(() if fault == 'samples' else (item,), **kwargs)
    assert _same(state, actor.state_dict())


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
def test_original_checked_rollout_retains_mandatory_idle_maintenance_and_undiscounted_reward(mode):
    data = ParallelMaintenanceInstance((ProductionTask(0, 2, 0),), 1,
        (MaintenanceRequirement(0, 2, 5, 9, 5),))
    episode = run_policy_episode(data, mode=mode, actor=_api().SharedScorer(seed=17), seed=29)
    assert len(episode.actions) == 2 and 96 in episode.actions
    assert episode.result.maintenance_records[0].start == 5
    assert episode.total_reward == pytest.approx(-episode.result.total_tardiness/100)
    assert all(sample.return_value == pytest.approx(math.fsum(episode.rewards[i:]))
               for i, sample in enumerate(episode.samples))
    assert all(len(sample.features) == 372 for sample in episode.samples)
