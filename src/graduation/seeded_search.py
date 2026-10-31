"""Improved GA started from external plans (learned-policy or rule rollouts).

``metaheuristics.py`` stays byte-identical because exp_040 binds it by
SHA-256. Here the IGA initial population is: the given seed sequences
first, then the six built-in heuristic sequences, then random fill. Seed
decodes count against the evaluation budget like any other decode.

A finished plan becomes a token sequence by listing its jobs and
maintenance activities in start-time order (maintenance first on ties).
The earliest-completion decoder may assign a job to a different machine
than the source plan did, so a seed can decode to a worse value; callers
should report how often the source value is reproduced.
"""

from __future__ import annotations

import random

from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.metaheuristics import (
    DEFAULT_SETTINGS, MetaheuristicError, SearchOutcome, _genetic, _Problem, _Tracker,
)
from src.graduation.result import MaintenanceScheduleResult


def plan_to_sequence(result: MaintenanceScheduleResult, data: ParallelMaintenanceInstance) -> list[int]:
    """Job and maintenance tokens of a plan in start-time order."""
    n = len(data.tasks)
    events = [(r.start, 1, r.job_id) for r in result.records]
    events += [(r.start, 0, n + r.machine_id) for r in result.maintenance_records]
    sequence = [token for _, _, token in sorted(events)]
    if sorted(sequence) != list(range(n + data.num_machines)):
        raise ValueError('Plan does not cover every job and maintenance exactly once')
    return sequence


def decoded_value(data: ParallelMaintenanceInstance, mode: str, sequence: list[int]) -> int:
    """Total tardiness of a sequence under the IGA decoder (not a search evaluation)."""
    return _Problem(data, mode).decode(sequence)


class _SeededProblem(_Problem):
    def __init__(self, data: ParallelMaintenanceInstance, mode: str, seeds: list[list[int]]):
        super().__init__(data, mode)
        size = self.n + self.m
        for sequence in seeds:
            if sorted(sequence) != list(range(size)):
                raise ValueError('Every seed must be a permutation of all job and maintenance tokens')
        self.seeds = [list(sequence) for sequence in seeds]

    def heuristic_sequences(self) -> list[list[int]]:
        return self.seeds + super().heuristic_sequences()


def solve_seeded_iga(data: ParallelMaintenanceInstance, *, mode: str, seeds: list[list[int]],
                     evaluations: int = 2000, seed: int = 0, settings: dict | None = None) -> SearchOutcome:
    """IGA whose initial population starts with ``seeds``; returns a G1-accepted plan."""
    if type(evaluations) is not int or evaluations < 1:
        raise ValueError('evaluations must be a positive integer')
    if type(seed) is not int:
        raise ValueError('seed must be an integer')
    problem = _SeededProblem(data, mode, seeds)
    config = {**DEFAULT_SETTINGS['IGA'], **(settings or {})}
    tracker = _Tracker(problem, evaluations)
    _genetic(tracker, problem, config, random.Random(seed), improved=True)
    if tracker.best_sequence is None:
        raise MetaheuristicError('No solution was evaluated')
    if problem.evaluations > evaluations:
        raise MetaheuristicError('Evaluation budget exceeded')
    return SearchOutcome('IGA-seeded', mode, seed, problem.evaluations, tracker.best_evaluation,
                         tuple(tracker.best_sequence), problem.result(tracker.best_sequence))
