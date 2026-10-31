"""Learned constructive policies: legal-only scoring, accepted plans, reproducible checkpoints."""

import math
import statistics

import numpy as np
import pytest

from fjsp_lab.maintenance import check_parallel_maintenance_feasibility
from fjsp_lab.maintenance.env import ParallelMaintenanceEnv, actions_for_plan
from fjsp_lab.maintenance.features import FEATURE_COUNT, action_candidates
from fjsp_lab.maintenance.generator import sample_instances
from fjsp_lab.maintenance.metaheuristics import solve_metaheuristic
from fjsp_lab.maintenance.scoring_policy import ScoringPolicy, best_of_rollouts, run_episode, train


def reference_rows(env):
    """Row-by-row definition of the 19 features (the vectorized code must match it)."""
    data, tails = env.data, env.machine_tails
    m, legal = data.num_machines, env.legal_actions()
    scale = (sum(t.processing_time for t in data.tasks) + m - 1) // m
    pbar = statistics.fmean(t.processing_time for t in data.tasks)
    remaining = [t for t in data.tasks if not env.scheduled[t.job_id]]
    dues, times = sorted(t.due_date for t in remaining), sorted(t.processing_time for t in remaining)
    span = max(1, len(remaining) - 1)
    job_tails = [tails[env.machine_of(a)] for a in legal if not env.is_maintenance(a)]
    next_start = min(job_tails) if job_tails else min(tails)
    rows = []
    for a in legal:
        x = [0.0] * FEATURE_COUNT
        x[10:13] = [float(env.mode == 'joint'), len(remaining) / len(data.tasks),
                    sum(t.processing_time for t in remaining) / m / scale]
        machine, t = env.machine_of(a), tails[env.machine_of(a)]
        pending = env.pending_window(machine) is not None
        if not env.is_maintenance(a):
            p, d = data.tasks[env.job_of(a)].processing_time, data.tasks[env.job_of(a)].due_date
            x[0:9] = [1.0, p / pbar, (d - t) / scale, max(0, t + p - d) / scale, (max(d, t + p) - t) / scale,
                      math.exp(-max(0, d - p - t) / pbar) * pbar / p, (t - min(tails)) / scale, float(pending),
                      (env.job_limit(machine) - t - p) / scale if pending else 0.0]
            x[13], x[14] = dues.index(d) / span, times.index(p) / span
        else:
            start = env.maintenance_start(machine)
            x[9] = 1.0
            x[15:19] = [(start - t) / scale, (env.job_limit(machine) - t) / scale, (start - min(tails)) / scale,
                        float(start < next_start)]
        rows.append([min(5.0, max(-5.0, v)) for v in x])
    return np.array(rows)


@pytest.mark.parametrize('fixture', ['large', 'periodic'])
def test_vectorized_features_match_their_definition_along_random_trajectories(fixture, request):
    data, rng = request.getfixturevalue(fixture), np.random.default_rng(0)
    for mode in ('fixed', 'joint'):
        env = ParallelMaintenanceEnv(data, mode=mode)
        while not env.done:
            legal, rows = action_candidates(env)
            assert legal == env.legal_actions() and rows.shape == (len(legal), FEATURE_COUNT)
            assert np.array_equal(rows, reference_rows(env))
            env.step(legal[int(rng.integers(len(legal)))])


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
@pytest.mark.parametrize('fixture', ['large', 'periodic_big'])
def test_scoring_policy_plans_are_accepted_and_sampling_never_hurts(mode, fixture, request):
    large = request.getfixturevalue(fixture)
    policy = ScoringPolicy(seed=0)
    greedy = run_episode(policy, large, mode=mode)
    best = best_of_rollouts(policy, large, mode=mode, samples=2, seed=1)
    for plan in (greedy.result, best):
        ok, violations = check_parallel_maintenance_feasibility(plan, large, mode=mode)
        assert ok is True, violations
    assert best.total_tardiness <= greedy.total_tardiness


def test_scoring_policy_checkpoint_round_trip(tmp_path, large):
    policy = ScoringPolicy(seed=4, hidden_size=8)
    digest = policy.save(tmp_path / 'p.npz')
    loaded = ScoringPolicy.load(tmp_path / 'p.npz', expected_sha256=digest)
    assert run_episode(loaded, large, mode='joint').total_tardiness == run_episode(policy, large, mode='joint').total_tardiness
    with pytest.raises(ValueError):
        ScoringPolicy.load(tmp_path / 'p.npz', expected_sha256='0' * 64)


def test_short_training_is_reproducible_and_selects_on_validation():
    train_set = sample_instances(range(500, 512), sampler_seed=1, sizes=((8, 2),))
    val_set = sample_instances(range(600, 606), sampler_seed=2, sizes=((8, 2),))
    a, history = train(train_set, val_set, seed=0, hidden_size=8, bc_epochs=2, rl_epochs=1)
    b, again = train(train_set, val_set, seed=0, hidden_size=8, bc_epochs=2, rl_epochs=1)
    assert history == again and all(np.array_equal(x, y) for x, y in zip(a.state_dict().values(), b.state_dict().values()))
    assert history[-1]['phase'] == 'selected'
    assert history[-1]['val_mean_tardiness'] == min(h['val_mean_tardiness'] for h in history[:-1])


def test_attention_policy_rollout_imitation_and_checkpoint(tmp_path, small, periodic):
    torch = pytest.importorskip('torch')
    from fjsp_lab.maintenance.attention_policy import (
        AttentionPolicy, PolicyConfig, imitation_loss, load, reinforce_loss, rollout, save,
    )
    torch.manual_seed(0)
    model = AttentionPolicy(PolicyConfig(width=32, layers=1, heads=4, feedforward=64))
    problems = [(small, 'fixed'), (periodic, 'joint')]
    greedy, _ = rollout(model, problems, samples=2, greedy=True)
    assert greedy[0][0] == greedy[0][1] and all(v >= 0 for g in greedy for v in g)
    teachers = [actions_for_plan(solve_metaheuristic(d, mode=m, algorithm='IGA', evaluations=200).result, d, m)
                for d, m in problems]
    loss = imitation_loss(model, problems, teachers)
    loss.backward()
    assert loss.item() > 0
    rl, mean = reinforce_loss(model, problems, samples=3, generator=torch.Generator().manual_seed(1), scale=[1.0, 1.0])
    rl.backward()
    assert mean >= 0
    digest = save(model.eval(), tmp_path / 'm.pt')
    again = load(tmp_path / 'm.pt', expected_sha256=digest)
    assert rollout(again, problems, samples=1, greedy=True)[0] == rollout(model, problems, samples=1, greedy=True)[0]
    with pytest.raises(ValueError):
        load(tmp_path / 'm.pt', expected_sha256='0' * 64)
