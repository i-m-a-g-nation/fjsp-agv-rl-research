"""L2 learned policy: legal and checked episodes, correct masked gradients, reproducible training."""

import numpy as np
import pytest

from fjsp_lab.fjsp import FJSPInstance
from fjsp_lab.logistics import LogisticsInstance, check_logistics_feasibility
from fjsp_lab.logistics.generator import CONFIGS, SPLITS, generate, split
from fjsp_lab.logistics.policy import (
    COLUMN, FEATURE_COUNT, Decision, LogisticsPolicy, best_rule, candidate_features, imitation_samples,
    run_episode, scale, train,
)
from fjsp_lab.logistics.simulator import LogisticsSimulator


def layout(m, unit=3):
    return [[0 if a == b else unit * (1 + abs(a - b)) for b in range(m + 1)] for a in range(m + 1)]


LAYOUTS = {k: layout(k) for k in (3, 4)}


def test_generator_is_deterministic_disjoint_and_covers_the_configurations():
    assert generate(5, LAYOUTS) == generate(5, LAYOUTS)
    train_set, val_set = split('train', 40, LAYOUTS), split('validation', 5, LAYOUTS)
    assert {g.seed for g in train_set}.isdisjoint(g.seed for g in val_set)
    assert train_set[0].seed == SPLITS['train']
    assert {g.config for g in train_set} == set(CONFIGS)
    for g in train_set:
        blocking, buffer = CONFIGS[g.config]
        assert g.data.blocking == blocking and set(g.data.buffer_capacity) == {buffer}


def test_features_describe_the_candidates():
    data = generate(3, LAYOUTS).data
    sim = LogisticsSimulator(data)
    options = sim.candidates()
    rows = candidate_features(sim, options, scale(data))
    assert rows.shape == (len(options), FEATURE_COUNT) and np.all(np.isfinite(rows))
    assert not rows[:, COLUMN['is_stay']].any()                     # at time 0 every job is at L/U
    eft = min(range(len(options)), key=lambda i: options[i].finish)
    assert rows[eft, COLUMN['finish_rank']] == rows[:, COLUMN['finish_rank']].min()


def test_episodes_are_checked_and_reproducible():
    policy = LogisticsPolicy(seed=1)
    for g in split('train', 10, LAYOUTS):
        greedy = run_episode(policy, g.data)
        assert check_logistics_feasibility(greedy.schedule, g.data)[0] is True
        assert run_episode(policy, g.data).schedule == greedy.schedule
        a = run_episode(policy, g.data, rng=np.random.default_rng(7), record=True)
        b = run_episode(policy, g.data, rng=np.random.default_rng(7), record=True)
        assert a.schedule == b.schedule and len(a.decisions) == len(b.decisions) > 0


def test_masking_avoids_deadlock_where_plain_choices_would_deadlock():
    crossing = FJSPInstance.from_jobs_array([[[(0, 2)], [(1, 2)]], [[(1, 2)], [(0, 2)]]], num_machines=2)
    data = LogisticsInstance.create(crossing, layout(2, 1), num_vehicles=2, buffer_capacity=0)
    for seed in range(5):
        episode = run_episode(LogisticsPolicy(seed=seed), data, rng=np.random.default_rng(seed))
        assert check_logistics_feasibility(episode.schedule, data)[0] is True


def test_masked_gradient_matches_finite_differences():
    policy = LogisticsPolicy(seed=3, hidden_size=5)
    rng = np.random.default_rng(0)
    features = rng.normal(size=(4, FEATURE_COUNT))
    mask = np.array([True, False, True, True])
    hidden, probabilities = policy.forward(features, mask)
    assert probabilities[1] == 0.0
    analytic = policy.grad_log_probability(Decision(features, hidden, probabilities, 2))

    def log_p() -> float:
        return float(np.log(policy.forward(features, mask)[1][2]))
    for name in ('W1', 'b1', 'w2'):
        value = getattr(policy, name)
        index = (0,) * value.ndim
        original = value[index]
        value[index] = original + 1e-6
        up = log_p()
        value[index] = original - 1e-6
        down = log_p()
        value[index] = original
        assert analytic[name][index] == pytest.approx((up - down) / 2e-6, rel=1e-4, abs=1e-7)


def test_imitation_samples_follow_the_best_rule(tmp_path):
    instances = [g.data for g in split('train', 3, LAYOUTS)]
    samples = imitation_samples(instances)
    assert samples and all(0 <= choice < len(features) for features, choice in samples)
    policy = LogisticsPolicy(seed=0)
    digest = policy.save(tmp_path / 'p.npz')
    again = LogisticsPolicy.load(tmp_path / 'p.npz', expected_sha256=digest)
    assert run_episode(again, instances[0]).schedule == run_episode(policy, instances[0]).schedule
    with pytest.raises(ValueError):
        LogisticsPolicy.load(tmp_path / 'p.npz', expected_sha256='0' * 64)


def test_training_is_reproducible_and_selects_on_validation():
    train_set = [g.data for g in split('train', 6, LAYOUTS)]
    val_set = [g.data for g in split('validation', 3, LAYOUTS)]
    first, history = train(train_set, val_set, seed=4, bc_epochs=2, rl_epochs=2, samples_per_instance=2)
    second, _ = train(train_set, val_set, seed=4, bc_epochs=2, rl_epochs=2, samples_per_instance=2)
    assert all(np.array_equal(first.state_dict()[k], second.state_dict()[k]) for k in first.state_dict())
    assert history[-1]['phase'] == 'selected'
    assert history[-1]['val_ratio_to_best_rule'] == min(h['val_ratio_to_best_rule'] for h in history[:-1])
    assert best_rule(val_set[0])[1] > 0


def test_parallel_training_matches_serial_training_exactly():
    train_set = [g.data for g in split('train', 4, LAYOUTS)]
    val_set = [g.data for g in split('validation', 2, LAYOUTS)]
    kwargs = dict(seed=6, bc_epochs=1, rl_epochs=2, samples_per_instance=2, rl_batch_size=2)
    serial, serial_history = train(train_set, val_set, workers=1, **kwargs)
    parallel, parallel_history = train(train_set, val_set, workers=2, **kwargs)
    assert all(np.array_equal(serial.state_dict()[k], parallel.state_dict()[k]) for k in serial.state_dict())
    assert serial_history == parallel_history
