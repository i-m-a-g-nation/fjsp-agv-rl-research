"""GA, SA and improved GA (IGA) for parallel machines with mandatory maintenance.

A solution is one permutation of the n job tokens (0..n-1) and one token
per maintenance window (n.., machine-major, windows in time order). The list
decoder reads it left to right:

* a job goes to the machine where it completes earliest. On that machine it
  may run before the next pending maintenance only if that maintenance still
  fits afterwards (fixed: end <= f_ik; joint: end <= U_ik - q_ik); otherwise
  the pending maintenance (and, if needed, the following ones) is inserted
  first and the job follows it;
* a maintenance token schedules that window's maintenance now (fixed: at
  f_ik; joint: at max(tail, L_ik)), together with any earlier pending
  windows of the machine, unless it was already inserted;
* windows still pending at the end are maintained last, in order.

These rules keep every decoded plan inside the windows, so search never
needs repair or penalties. The decoder has no size cap (unlike the
construction environment). All three solvers share one evaluation budget
(decodes, local-search moves included) and return only checker-accepted
plans. GA and IGA can start from given sequences (e.g. a learned policy's
plans via ``plan_to_sequence``), placed first in the initial population.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

from fjsp_lab.maintenance.feasibility import build_plan, require_feasible, validate_problem
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult

ALGORITHMS = ('GA', 'SA', 'IGA')
DEFAULT_SETTINGS = {
    'GA': {'population': 40, 'tournament': 3, 'crossover_rate': 0.9, 'mutation_rate': 0.2, 'elites': 2},
    'SA': {'final_temperature_ratio': 1e-3, 'initial_acceptance': 0.5, 'calibration_moves': 20},
    'IGA': {'population': 40, 'tournament': 3, 'crossover_rate': 0.9, 'mutation_rate': 0.2, 'elites': 2,
            'local_search_moves': 20},
}


class MetaheuristicError(RuntimeError):
    """A metaheuristic could not return an accepted plan."""


@dataclass(frozen=True)
class SearchOutcome:
    """Best accepted plan with its search trace."""

    algorithm: str
    mode: str
    seed: int
    evaluations: int
    best_evaluation: int
    sequence: tuple[int, ...]
    result: MaintenanceScheduleResult


class _Problem:
    """Integer arrays and the list decoder for one instance and mode."""

    def __init__(self, data: ParallelMaintenanceInstance, mode: str, initial: list[list[int]] = ()):
        validate_problem(data, mode)
        self.data, self.mode = data, mode
        self.n, self.m = len(data.tasks), data.num_machines
        self.p = [task.processing_time for task in data.tasks]
        self.d = [task.due_date for task in data.tasks]
        fixed = mode == 'fixed'
        # Per machine and window: duration, window start, latest end of a job
        # that runs before this maintenance, and the fixed start.
        self.q = [[item.duration for item in windows] for windows in data.windows]
        self.lo = [[item.window_start for item in windows] for windows in data.windows]
        self.limit = [[item.fixed_start if fixed else item.window_end - item.duration for item in windows]
                      for windows in data.windows]
        self.fixed_start = [[item.fixed_start for item in windows] for windows in data.windows]
        # Maintenance token n + i stands for window self.token_window[i] of self.token_machine[i].
        self.token_machine = [machine for machine, windows in enumerate(data.windows) for _ in windows]
        self.token_window = [k for windows in data.windows for k in range(len(windows))]
        self.size = self.n + len(self.token_machine)
        self.evaluations = 0
        for sequence in initial:
            if sorted(sequence) != list(range(self.size)):
                raise ValueError('Every initial sequence must be a permutation of all job and maintenance tokens')
        self.initial = [list(sequence) for sequence in initial]

    def _maintenance_start(self, machine: int, window: int, tail: int) -> int:
        return self.fixed_start[machine][window] if self.mode == 'fixed' else max(tail, self.lo[machine][window])

    def decode(self, sequence, plan: bool = False):
        """Total tardiness of a token sequence; with plan=True also the placements."""
        self.evaluations += 1
        n, m, p, d, q, limit = self.n, self.m, self.p, self.d, self.q, self.limit
        counts = [len(windows) for windows in q]
        tails, nxt = [0] * m, [0] * m
        jobs, maintenance, total = [], [], 0
        for token in sequence:
            if token < n:
                duration, best = p[token], None
                for machine in range(m):
                    start, k, inserted = tails[machine], nxt[machine], None
                    while k < counts[machine] and start + duration > limit[machine][k]:
                        start_m = self._maintenance_start(machine, k, start)
                        inserted = (inserted or []) + [(machine, k, start_m)]
                        start = start_m + q[machine][k]
                        k += 1
                    if best is None or start + duration < best[0]:
                        best = (start + duration, machine, start, inserted, k)
                end, machine, start, inserted, k = best
                if inserted:
                    maintenance += inserted
                    nxt[machine] = k
                tails[machine] = end
                if end > d[token]:
                    total += end - d[token]
                if plan:
                    jobs.append((token, machine, start))
            else:
                machine, window = self.token_machine[token - n], self.token_window[token - n]
                while nxt[machine] <= window:
                    k = nxt[machine]
                    start_m = self._maintenance_start(machine, k, tails[machine])
                    maintenance.append((machine, k, start_m))
                    tails[machine] = start_m + q[machine][k]
                    nxt[machine] = k + 1
        for machine in range(m):
            for k in range(nxt[machine], counts[machine]):
                start_m = self._maintenance_start(machine, k, tails[machine])
                maintenance.append((machine, k, start_m))
                tails[machine] = start_m + q[machine][k]
        return (total, jobs, maintenance) if plan else total

    def result(self, sequence) -> MaintenanceScheduleResult:
        """Build, independently re-score and check the decoded plan."""
        total, jobs, maintenance = self.decode(sequence, plan=True)
        self.evaluations -= 1  # building the final plan is not a search evaluation
        result = build_plan(self.data, jobs, maintenance)
        if result.total_tardiness != total:
            raise MetaheuristicError('Decoder tardiness differs from independent recomputation')
        return require_feasible(result, self.data, mode=self.mode, source='Metaheuristic')

    def heuristic_sequences(self) -> list[list[int]]:
        """EDD, SPT and slack orders; first-window tokens first or all maintenance tokens last."""
        jobs = range(self.n)
        orders = [sorted(jobs, key=lambda j: (self.d[j], self.p[j], j)),
                  sorted(jobs, key=lambda j: (self.p[j], self.d[j], j)),
                  sorted(jobs, key=lambda j: (self.d[j] - self.p[j], j))]
        tokens = list(range(self.n, self.size))
        first = [t for t in tokens if self.token_window[t - self.n] == 0]
        later = [t for t in tokens if self.token_window[t - self.n] > 0]
        return [variant for order in orders for variant in (first + order + later, order + tokens)]


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
    size = problem.size
    seeds = problem.initial + (problem.heuristic_sequences() if improved else [])
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
                        evaluations: int = 2000, seed: int = 0, settings: dict | None = None,
                        initial_sequences: list[list[int]] = ()) -> SearchOutcome:
    """Run GA, SA or IGA under an evaluation budget; return the accepted best plan."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f'algorithm must be one of {ALGORITHMS}')
    if type(evaluations) is not int or evaluations < 1:
        raise ValueError('evaluations must be a positive integer')
    if type(seed) is not int:
        raise ValueError('seed must be an integer')
    if initial_sequences and algorithm == 'SA':
        raise ValueError('initial_sequences apply to GA and IGA only')
    problem = _Problem(data, mode, list(initial_sequences))
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


def plan_to_sequence(result: MaintenanceScheduleResult, data: ParallelMaintenanceInstance) -> list[int]:
    """Job and maintenance tokens of a plan in start-time order (maintenance first on ties).

    The earliest-completion decoder may put a job on a different machine than
    the source plan did, so the decoded value can be worse than the plan's.
    """
    n = len(data.tasks)
    first_token = [n]
    for windows in data.windows:
        first_token.append(first_token[-1] + len(windows))
    events = [(r.start, 1, r.job_id) for r in result.records]
    events += [(r.start, 0, first_token[r.machine_id] + r.window) for r in result.maintenance_records]
    sequence = [token for _, _, token in sorted(events)]
    if sorted(sequence) != list(range(n + data.num_windows)):
        raise ValueError('Plan does not cover every job and maintenance exactly once')
    return sequence


def decoded_value(data: ParallelMaintenanceInstance, mode: str, sequence: list[int]) -> int:
    """Total tardiness of a token sequence under the decoder."""
    return _Problem(data, mode).decode(sequence)
