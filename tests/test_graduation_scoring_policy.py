import copy
import json

import numpy as np
import pytest

from src.graduation import check_parallel_maintenance_feasibility
from src.graduation.action_features import FEATURE_COUNT, FEATURE_NAMES, action_candidates
from src.graduation.dispatch_rules import DISPATCH_RULES, rule_action, solve_dispatch_rule
from src.graduation.enumeration import enumerate_parallel_maintenance
from src.graduation.rl_environment import MAINTENANCE_OFFSET, ParallelMaintenanceEnv
from src.graduation.scoring_policy import Decision, ScoringPolicy, run_episode
from src.graduation.scoring_training import (
    behaviour_cloning_epoch, imitation_samples, make_instances, rule_tardiness, train,
)
from tests.graduation_helpers import one_machine, two_machines


@pytest.mark.parametrize('builder', [one_machine, two_machines])
@pytest.mark.parametrize('mode', ['fixed', 'joint'])
@pytest.mark.parametrize('rule', DISPATCH_RULES)
def test_dispatch_rules_return_checked_plans_no_better_than_optimum(builder, mode, rule):
    data, _ = builder()
    result = solve_dispatch_rule(data, mode=mode, rule=rule)
    assert check_parallel_maintenance_feasibility(result, data, mode=mode) == (True, [])
    assert result.total_tardiness >= enumerate_parallel_maintenance(data, mode=mode).total_tardiness


def test_unknown_rule_is_rejected():
    data, _ = one_machine()
    with pytest.raises(ValueError):
        solve_dispatch_rule(data, mode='joint', rule='LPT')


def test_features_follow_mask_and_encode_the_rule_maintenance_decision():
    instance = make_instances(range(30000, 30006), sampler_seed=3, balanced=True)[1]
    env = ParallelMaintenanceEnv(instance.data, mode=instance.mode)
    while True:
        legal, rows = action_candidates(env)
        assert legal == [a for a, ok in enumerate(env.action_masks()) if ok]
        assert rows.shape == (len(legal), FEATURE_COUNT) == (len(legal), len(FEATURE_NAMES))
        assert np.all(np.isfinite(rows)) and np.all(np.abs(rows) <= 5.0)
        assert all(rows[k, 0] + rows[k, 9] == 1.0 for k in range(len(legal)))
        action = rule_action(env, legal, 'MDD')
        if action >= MAINTENANCE_OFFSET and any(a < MAINTENANCE_OFFSET for a in legal):
            assert rows[legal.index(action), 18] == 1.0
        if env.step(action).terminated:
            break


def test_gradient_matches_finite_differences():
    rng = np.random.default_rng(0)
    policy = ScoringPolicy(seed=1, hidden_size=5)
    features = rng.normal(size=(4, FEATURE_COUNT))
    hidden, probabilities = policy.forward(features)
    gradient = policy.grad_log_probability(Decision(features, hidden, probabilities, 2))
    for name in ('W1', 'b1', 'w2'):
        values = getattr(policy, name)
        index = (0,) * values.ndim
        original = values[index]
        values[index] = original + 1e-6
        up = np.log(policy.forward(features)[1][2])
        values[index] = original - 1e-6
        down = np.log(policy.forward(features)[1][2])
        values[index] = original
        assert gradient[name][index] == pytest.approx((up - down) / 2e-6, rel=1e-4, abs=1e-8)


def test_probabilities_are_normalized_and_nonfinite_updates_are_rejected():
    policy = ScoringPolicy(seed=0)
    _, probabilities = policy.forward(np.ones((3, FEATURE_COUNT)))
    assert probabilities.sum() == pytest.approx(1.0)
    with pytest.raises(ValueError):
        policy.forward(np.ones((3, FEATURE_COUNT + 1)))
    bad = {name: np.full_like(getattr(policy, name), np.nan) for name in ('W1', 'b1', 'w2')}
    with pytest.raises(FloatingPointError):
        policy.ascend(bad, 1e-3)


def test_checkpoint_round_trip_and_hash_binding(tmp_path):
    policy = ScoringPolicy(seed=3, hidden_size=7)
    digest = policy.save(tmp_path / 'p.npz')
    loaded = ScoringPolicy.load(tmp_path / 'p.npz', expected_sha256=digest)
    for name in ('W1', 'b1', 'w2'):
        assert np.array_equal(getattr(loaded, name), getattr(policy, name))
    with pytest.raises(ValueError):
        ScoringPolicy.load(tmp_path / 'p.npz', expected_sha256='0' * 64)


def test_episodes_are_checked_and_reproducible():
    instance = make_instances(range(30000, 30012), sampler_seed=3, balanced=True)[5]
    policy = ScoringPolicy(seed=0)
    greedy = [run_episode(policy, instance.data, mode=instance.mode) for _ in range(2)]
    assert greedy[0].result.records == greedy[1].result.records
    sampled = [run_episode(policy, instance.data, mode=instance.mode, rng=np.random.default_rng(7), record=True)
               for _ in range(2)]
    assert sampled[0].total_tardiness == sampled[1].total_tardiness
    assert len(sampled[0].decisions) == instance.num_tasks + instance.num_machines
    for episode in greedy + sampled:
        assert check_parallel_maintenance_feasibility(episode.result, instance.data, mode=instance.mode) == (True, [])


def test_splits_are_disjoint_and_balanced():
    train_set = make_instances(range(10000, 10030), sampler_seed=1)
    test_set = make_instances(range(30000, 30012), sampler_seed=3, balanced=True)
    assert not {i.seed for i in train_set} & {i.seed for i in test_set}
    assert [(i.num_tasks, i.num_machines) for i in test_set[:6]] == [(8, 2), (8, 4), (16, 2), (16, 4), (24, 2), (24, 4)]


def test_imitation_follows_best_rule_and_cloning_reduces_loss():
    instances = make_instances(range(10000, 10010), sampler_seed=1)
    samples = imitation_samples(instances)
    assert len(samples) == sum(i.num_tasks + i.num_machines for i in instances)
    assert all(0 <= choice < len(features) for features, choice in samples)
    policy = ScoringPolicy(seed=0)
    rng = np.random.default_rng(0)
    losses = [behaviour_cloning_epoch(policy, samples, rng=rng, learning_rate=3e-3) for _ in range(5)]
    assert losses[-1] < losses[0]
    assert min(rule_tardiness(instances[0]).values()) >= 0


def test_training_restores_the_best_validation_checkpoint():
    train_set = make_instances(range(10000, 10012), sampler_seed=1)
    val_set = make_instances(range(20000, 20006), sampler_seed=2)
    policy, history = train(train_set, val_set, seed=0, hidden_size=8, bc_epochs=2, rl_epochs=1)
    selected = history[-1]
    assert selected['phase'] == 'selected'
    assert selected['val_mean_tardiness'] == min(h['val_mean_tardiness'] for h in history[:-1])
    from src.graduation.scoring_training import mean_greedy_tardiness
    assert mean_greedy_tardiness(policy, val_set) == selected['val_mean_tardiness']


def test_exp_036_smoke(tmp_path):
    from experiments import exp_036_scoring_policy as experiment
    protocol = copy.deepcopy(experiment.PROTOCOL)
    protocol['train']['seeds'] = [10000, 10012]
    protocol['validation']['seeds'] = [20000, 20006]
    protocol['test']['seeds'] = [30000, 30012]
    protocol['training_seeds'] = [0, 1]
    protocol['hyperparameters'].update(hidden_size=8, bc_epochs=1, rl_epochs=1)
    manifest = experiment.run_experiment(tmp_path / 'out', protocol)
    assert manifest['split_sizes'] == {'train': 12, 'validation': 6, 'test': 12}
    assert set(manifest['checkpoint_sha256']) == {'policy_s0', 'policy_s1'}
    assert manifest['external_g3_primary']['n8_optimal_rows'] == 160
    gaps = manifest['external_g3_primary']['n8_mean_gap_to_optimum']
    assert all(value >= 0 for value in gaps.values())
    assert json.loads((tmp_path / 'out' / 'training_log.json').read_text(encoding='utf-8'))
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path / 'out', protocol)


def test_atc_k_parameter_and_portfolio():
    from src.graduation.dispatch_rules import RULE_PORTFOLIO
    instance = make_instances(range(30000, 30006), sampler_seed=3, balanced=True)[4]
    default = solve_dispatch_rule(instance.data, mode=instance.mode, rule='ATC')
    explicit = solve_dispatch_rule(instance.data, mode=instance.mode, rule='ATC', atc_k=1.0)
    assert default.records == explicit.records
    assert len(RULE_PORTFOLIO) == 9 and len(set(RULE_PORTFOLIO)) == 9
    for bad in (0, -1.0, float('nan'), True):
        with pytest.raises(ValueError):
            solve_dispatch_rule(instance.data, mode=instance.mode, rule='ATC', atc_k=bad)


def test_best_of_rollouts_never_worse_than_greedy_and_is_reproducible():
    from src.graduation.scoring_policy import best_of_rollouts
    instance = make_instances(range(30000, 30006), sampler_seed=3, balanced=True)[4]
    policy = ScoringPolicy(seed=0)
    greedy = run_episode(policy, instance.data, mode=instance.mode).result
    assert best_of_rollouts(policy, instance.data, mode=instance.mode, samples=0, seed=0).records == greedy.records
    best = [best_of_rollouts(policy, instance.data, mode=instance.mode, samples=6, seed=3) for _ in range(2)]
    assert best[0].records == best[1].records
    assert best[0].total_tardiness <= greedy.total_tardiness
    assert check_parallel_maintenance_feasibility(best[0], instance.data, mode=instance.mode) == (True, [])
    with pytest.raises(ValueError):
        best_of_rollouts(policy, instance.data, mode=instance.mode, samples=-1, seed=0)


def test_exp_037_smoke(tmp_path):
    from experiments import exp_037_sampling_decoding as experiment
    protocol = copy.deepcopy(experiment.PROTOCOL)
    protocol['test']['seeds'] = [40000, 40006]
    manifest = experiment.run_experiment(tmp_path / 'out', protocol)
    assert manifest['test_instances'] == 6
    means = manifest['test_summary']['means']['all']
    for name in ('policy_s0', 'policy_s1', 'policy_s2'):
        assert means[f'{name}_r9'] <= means[f'{name}_r3'] <= means[f'{name}_r1']
    assert means['best_of_9_rules'] <= means['best_of_3_rules'] <= means['MDD']
    gaps = manifest['external_g3_n8']['mean_gap_to_optimum']
    assert manifest['external_g3_n8']['instances'] == 160 and min(gaps.values()) >= 0
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path / 'out', protocol)
