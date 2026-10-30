"""Datasets, behaviour cloning and self-critical REINFORCE for ScoringPolicy.

Instances come from the G3A generator with disjoint seed ranges per split,
so no training workload reappears in validation or test. Training first
imitates, per instance, the best of the EDD/MDD/ATC dispatch rules, then
fine-tunes with REINFORCE using the greedy rollout as baseline (advantage
= (T_greedy - T_sample) / max(1, T_greedy)). Validation alone selects the
checkpoint; the test split is never touched here.
"""

from dataclasses import dataclass
import random
import statistics

import numpy as np

from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.dispatch_rules import DISPATCH_RULES, rule_action, solve_dispatch_rule
from src.graduation.action_features import action_candidates
from src.graduation.reference_main_protocol import _build_case, main_protocol
from src.graduation.reference_main_results import _data
from src.graduation.reference_protocol import _base_workload
from src.graduation.rl_environment import ParallelMaintenanceEnv
from src.graduation.scoring_policy import PARAMETERS, Decision, ScoringPolicy, run_episode

SIZES = ((8, 2), (8, 4), (16, 2), (16, 4), (24, 2), (24, 4))


@dataclass(frozen=True)
class Instance:
    data: ParallelMaintenanceInstance
    mode: str
    num_tasks: int
    num_machines: int
    alpha_percent: int
    beta_percent: int
    tau_percent: int
    seed: int


def make_instances(seeds: range, *, sizes=SIZES, sampler_seed: int, balanced: bool = False) -> list[Instance]:
    """Draw factors per seed; balanced cycles sizes, otherwise samples them."""
    rng = random.Random(sampler_seed)
    generator, solver = main_protocol()['generator'], main_protocol()['solver']
    instances = []
    for index, seed in enumerate(seeds):
        n, m = sizes[index % len(sizes)] if balanced else rng.choice(sizes)
        alpha, beta, tau = rng.choice((10, 30)), rng.choice((25, 75)), rng.choice((75, 125))
        mode = rng.choice(('fixed', 'joint'))
        case = _build_case(n, m, alpha, beta, tau, seed, 'window_midpoint', 'generated',
                           _base_workload(n, seed, generator), solver)
        instances.append(Instance(_data(case), mode, n, m, alpha, beta, tau, seed))
    return instances


def rule_tardiness(instance: Instance) -> dict[str, int]:
    return {rule: solve_dispatch_rule(instance.data, mode=instance.mode, rule=rule).total_tardiness
            for rule in DISPATCH_RULES}


def mean_greedy_tardiness(policy: ScoringPolicy, instances: list[Instance]) -> float:
    return statistics.fmean(run_episode(policy, i.data, mode=i.mode).total_tardiness for i in instances)


def imitation_samples(instances: list[Instance]) -> list[tuple[np.ndarray, int]]:
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


def reinforce_epoch(policy: ScoringPolicy, instances: list[Instance], *, rng: np.random.Generator,
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


def train(train_set: list[Instance], val_set: list[Instance], *, seed: int, hidden_size: int = 32,
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
