"""GA, SA and improved GA (IGA) for parallel machines with mandatory maintenance.

A solution is one permutation of the n job tokens (0..n-1) and the m
maintenance tokens (n..n+m-1). The list decoder reads it left to right:

* a job goes to the machine where it completes earliest. On a machine not
  yet maintained, it may run before maintenance only if maintenance still
  fits afterwards (fixed: end <= f_i; joint: end <= U_i - q_i); otherwise
  that machine's maintenance is inserted first and the job follows it;
* a maintenance token schedules that machine's maintenance now (fixed: at
  f_i; joint: at max(tail, L_i)) unless it was already inserted;
* machines still unmaintained at the end are maintained last.

These rules keep every decoded plan inside the windows, so search never
needs repair or penalties. The decoder has no size cap (unlike the R1
environment). All three solvers share one evaluation budget (decodes,
local-search moves included) and return only G1-accepted plans.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

from src.graduation.data import ParallelMaintenanceInstance, to_fjsp_instance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult

ALGORITHMS = ('GA', 'SA', 'IGA')
DEFAULT_SETTINGS = {
    'GA': {'population': 40, 'tournament': 3, 'crossover_rate': 0.9, 'mutation_rate': 0.2, 'elites': 2},
    'SA': {'final_temperature_ratio': 1e-3, 'initial_acceptance': 0.5, 'calibration_moves': 20},
    'IGA': {'population': 40, 'tournament': 3, 'crossover_rate': 0.9, 'mutation_rate': 0.2, 'elites': 2,
            'local_search_moves': 20},
}


class MetaheuristicError(RuntimeError):
    """A metaheuristic could not return a G1-accepted plan."""


@dataclass(frozen=True)
class SearchOutcome:
    """Best G1-accepted plan with its search trace."""

    algorithm: str
    mode: str
    seed: int
    evaluations: int
    best_evaluation: int
    sequence: tuple[int, ...]
    result: MaintenanceScheduleResult


class _Problem:
    """Integer arrays and the list decoder for one instance and mode."""

    def __init__(self, data: ParallelMaintenanceInstance, mode: str):
        if not isinstance(data, ParallelMaintenanceInstance) or mode not in ('fixed', 'joint'):
            raise ValueError('Expected typed G1 data and fixed/joint mode')
        if mode == 'fixed' and any(item.fixed_start is None for item in data.maintenance):
            raise ValueError('fixed mode requires every fixed_start')
        self.data, self.mode = data, mode
        self.n, self.m = len(data.tasks), data.num_machines
        self.p = [task.processing_time for task in data.tasks]
        self.d = [task.due_date for task in data.tasks]
        self.q = [item.duration for item in data.maintenance]
        self.lo = [item.window_start for item in data.maintenance]
        fixed = mode == 'fixed'
        # Latest time a job may end before maintenance on machine i.
        self.limit = [item.fixed_start if fixed else item.window_end - item.duration for item in data.maintenance]
        self.fixed_start = [item.fixed_start for item in data.maintenance]
        self.evaluations = 0

    def _maintenance_start(self, machine: int, tail: int) -> int:
        return self.fixed_start[machine] if self.mode == 'fixed' else max(tail, self.lo[machine])

    def decode(self, sequence, plan: bool = False):
        """Total tardiness of a token sequence; with plan=True also the placements."""
        self.evaluations += 1
        n, m, p, d, q, limit = self.n, self.m, self.p, self.d, self.q, self.limit
        tails, done = [0] * m, [False] * m
        jobs, maintenance, total = [], [], 0
        for token in sequence:
            if token < n:
                duration, best = p[token], None
                for machine in range(m):
                    tail, start_m = tails[machine], None
                    if done[machine] or tail + duration <= limit[machine]:
                        start = tail
                    else:
                        start_m = self._maintenance_start(machine, tail)
                        start = start_m + q[machine]
                    if best is None or start + duration < best[0]:
                        best = (start + duration, machine, start, start_m)
                end, machine, start, start_m = best
                if start_m is not None:
                    done[machine] = True
                    maintenance.append((machine, start_m))
                tails[machine] = end
                if end > d[token]:
                    total += end - d[token]
                if plan:
                    jobs.append((token, machine, start))
            else:
                machine = token - n
                if not done[machine]:
                    start_m = self._maintenance_start(machine, tails[machine])
                    done[machine] = True
                    maintenance.append((machine, start_m))
                    tails[machine] = start_m + q[machine]
        for machine in range(m):
            if not done[machine]:
                maintenance.append((machine, self._maintenance_start(machine, tails[machine])))
        return (total, jobs, maintenance) if plan else total

    def result(self, sequence) -> MaintenanceScheduleResult:
        """Build, independently re-score and G1-check the decoded plan."""
        total, jobs, maintenance = self.decode(sequence, plan=True)
        self.evaluations -= 1  # building the final plan is not a search evaluation
        result = MaintenanceScheduleResult(instance=to_fjsp_instance(self.data))
        for job, machine, start in jobs:
            result.add_record(job, 0, machine, start, self.p[job])
        result.maintenance_records = [MaintenanceRecord(machine, start, start + self.q[machine], self.q[machine])
                                      for machine, start in sorted(maintenance)]
        result.compute_makespan()
        result.total_tardiness = calculate_total_tardiness(self.data, result)
        if result.total_tardiness != total:
            raise MetaheuristicError('Decoder tardiness differs from independent recomputation')
        accepted, issues = check_parallel_maintenance_feasibility(result, self.data, mode=self.mode)
        if not accepted:
            raise MetaheuristicError(f'G1 rejected a decoded plan: {issues}')
        return result

    def heuristic_sequences(self) -> list[list[int]]:
        """EDD, SPT and slack orders, each with maintenance tokens first and last."""
        jobs = range(self.n)
        orders = [sorted(jobs, key=lambda j: (self.d[j], self.p[j], j)),
                  sorted(jobs, key=lambda j: (self.p[j], self.d[j], j)),
                  sorted(jobs, key=lambda j: (self.d[j] - self.p[j], j))]
        tokens = list(range(self.n, self.n + self.m))
        return [variant for order in orders for variant in (tokens + order, order + tokens)]


def _swap(sequence: list[int], rng: random.Random) -> list[int]:
    child = sequence[:]
    i, j = rng.sample(range(len(child)), 2)
    child[i], child[j] = child[j], child[i]
    return child


def _insert(sequence: list[int], rng: random.Random) -> list[int]:
    child = sequence[:]
    i, j = rng.sample(range(len(child)), 2)
    child.insert(j, child.pop(i))
    return child


def _neighbour(sequence: list[int], rng: random.Random) -> list[int]:
    return _swap(sequence, rng) if rng.random() < 0.5 else _insert(sequence, rng)


def _order_crossover(a: list[int], b: list[int], rng: random.Random) -> list[int]:
    """OX: keep a slice of parent a, fill the rest in parent b's order."""
    size = len(a)
    i, j = sorted(rng.sample(range(size + 1), 2))
    middle = a[i:j]
    kept = set(middle)
    rest = [token for token in b if token not in kept]
    return rest[:i] + middle + rest[i:]


class _Tracker:
    """Best-so-far bookkeeping under a hard evaluation budget."""

    def __init__(self, problem: _Problem, budget: int):
        self.problem, self.budget = problem, budget
        self.best_value, self.best_sequence, self.best_evaluation = None, None, 0

    @property
    def left(self) -> int:
        return self.budget - self.problem.evaluations

    def evaluate(self, sequence: list[int]) -> int:
        value = self.problem.decode(sequence)
        if self.best_value is None or value < self.best_value:
            self.best_value, self.best_sequence = value, sequence[:]
            self.best_evaluation = self.problem.evaluations
        return value


def _tournament(population: list[tuple[int, list[int]]], size: int, rng: random.Random) -> list[int]:
    return min(rng.sample(population, size), key=lambda item: item[0])[1]


def _local_search(tracker: _Tracker, value: int, sequence: list[int], moves: int,
                  rng: random.Random) -> tuple[int, list[int]]:
    """First-improvement insertion moves, each counted against the budget."""
    for _ in range(moves):
        if tracker.left <= 0 or value == 0:
            break
        candidate = _insert(sequence, rng)
        candidate_value = tracker.evaluate(candidate)
        if candidate_value <= value:
            value, sequence = candidate_value, candidate
    return value, sequence


def _genetic(tracker: _Tracker, problem: _Problem, settings: dict, rng: random.Random, improved: bool) -> None:
    size = problem.n + problem.m
    seeds = problem.heuristic_sequences() if improved else []
    starts = seeds[:settings['population']]
    while len(starts) < settings['population']:
        starts.append(rng.sample(range(size), size))
    population = []
    for sequence in starts:
        if tracker.left <= 0:
            return
        population.append((tracker.evaluate(sequence), sequence))
    while tracker.left > 0 and tracker.best_value > 0:
        population.sort(key=lambda item: item[0])
        offspring = population[:settings['elites']]
        while len(offspring) < settings['population'] and tracker.left > 0:
            a = _tournament(population, settings['tournament'], rng)
            if rng.random() < settings['crossover_rate']:
                child = _order_crossover(a, _tournament(population, settings['tournament'], rng), rng)
            else:
                child = a[:]
            if rng.random() < settings['mutation_rate']:
                child = _neighbour(child, rng)
            offspring.append((tracker.evaluate(child), child))
        if improved and tracker.left > 0:
            offspring.sort(key=lambda item: item[0])
            offspring[0] = _local_search(tracker, *offspring[0], settings['local_search_moves'], rng)
        population = offspring


def _annealing(tracker: _Tracker, problem: _Problem, settings: dict, rng: random.Random) -> None:
    current = problem.heuristic_sequences()[1]  # EDD order, maintenance tokens last
    value = tracker.evaluate(current)
    deltas = []
    for _ in range(min(settings['calibration_moves'], max(0, tracker.left - 1))):
        delta = tracker.evaluate(_neighbour(current, rng)) - value
        if delta > 0:
            deltas.append(delta)
    start_t = (sum(deltas) / len(deltas)) / -math.log(settings['initial_acceptance']) if deltas else 1.0
    steps = max(1, tracker.left)
    cooling = settings['final_temperature_ratio'] ** (1.0 / steps)
    temperature = start_t
    while tracker.left > 0 and tracker.best_value > 0:
        candidate = _neighbour(current, rng)
        candidate_value = tracker.evaluate(candidate)
        delta = candidate_value - value
        if delta <= 0 or rng.random() < math.exp(-delta / temperature):
            current, value = candidate, candidate_value
        temperature *= cooling


def solve_metaheuristic(data: ParallelMaintenanceInstance, *, mode: str, algorithm: str,
                        evaluations: int = 2000, seed: int = 0,
                        settings: dict | None = None) -> SearchOutcome:
    """Run GA, SA or IGA under an evaluation budget; return the G1-accepted best plan."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f'algorithm must be one of {ALGORITHMS}')
    if type(evaluations) is not int or evaluations < 1:
        raise ValueError('evaluations must be a positive integer')
    if type(seed) is not int:
        raise ValueError('seed must be an integer')
    problem = _Problem(data, mode)
    config = {**DEFAULT_SETTINGS[algorithm], **(settings or {})}
    rng = random.Random(seed)
    tracker = _Tracker(problem, evaluations)
    if algorithm == 'SA':
        _annealing(tracker, problem, config, rng)
    else:
        _genetic(tracker, problem, config, rng, improved=algorithm == 'IGA')
    if tracker.best_sequence is None:
        raise MetaheuristicError('No solution was evaluated')
    if problem.evaluations > evaluations:
        raise MetaheuristicError('Evaluation budget exceeded')
    return SearchOutcome(algorithm, mode, seed, problem.evaluations, tracker.best_evaluation,
                         tuple(tracker.best_sequence), problem.result(tracker.best_sequence))
